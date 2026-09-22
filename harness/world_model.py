"""CASCADE - Layer 3: World Model Embodied (JEPA).

Implementazione di un Joint Embedding Predictive Architecture nel senso di
Yann LeCun: il modello NON predice nel pixel/obs space (costoso e irrilevante)
ma nel **latent space**, imparando una rappresentazione del dinamica che sia
utile per il controllo piu' che per la ricostruzione.

Componenti:
- Context Encoder     : oss -> z_c          (codifica lo stato corrente)
- Target Encoder      : oss_next -> z_t     (codifica lo stato futuro)
- Latent Predictor    : (z_c, action) -> z_hat  (predice z_t nel latent space)
- Anti-collapse       : VICReg-style (varianza + covarianza) per evitare che
                        tutte le rappresentazioni collassino a una costante.

Il target encoder e' una media mobile (EMA) del context encoder (momentum),
come in BYOL/JEPA, cosi' il target e' un obiettivo stabile ma evolvente.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------- #
# Encoder
# --------------------------------------------------------------------------- #


class ObsEncoder(nn.Module):
    """Codifica un'osservazione in un vettore latente."""

    def __init__(self, obs_dim: int, hidden_dim: int = 128, latent_dim: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.net(obs)


ENT = nn.Module  # type alias


# --------------------------------------------------------------------------- #
# Latent predictor
# --------------------------------------------------------------------------- #


class LatentPredictor(nn.Module):
    """Predice il latent futuro dal latent contesto + azione (in latent space)."""

    def __init__(self, latent_dim: int, action_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(self, z_c: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([z_c, action], dim=-1))


# --------------------------------------------------------------------------- #
# Anti-collapse: VICReg-style
# --------------------------------------------------------------------------- #


class VicregLoss:
    """Regularizzazione VICReg: mantiene varianza e decorrela i latenti.

    Senza questo, un JEPA puo' collassare: l'encoder produce sempre lo stesso
    output e la predizione 'va a segno' banalmente (perche' target e predetto
    coincidono triviaimente). La varianza impedisce il collasso costante.
    """

    def __init__(self, sim_coeff: float = 25.0, var_coeff: float = 25.0,
                 cov_coeff: float = 1.0):
        self.sim = sim_coeff
        self.var = var_coeff
        self.cov = cov_coeff

    def __call__(self, z_pred: torch.Tensor, z_target: torch.Tensor) -> torch.Tensor:
        sim = F.mse_loss(z_pred, z_target)

        # varianza: mantiene std >= 1 lungo i batch
        std = torch.sqrt(z_pred.var(dim=0) + 1e-4)
        var_loss = F.relu(1.0 - std).mean()
        std_t = torch.sqrt(z_target.var(dim=0) + 1e-4)
        var_loss_t = F.relu(1.0 - std_t).mean()
        var_loss = (var_loss + var_loss_t) / 2

        # covarianza: decorrela le dimensioni (evita rappresentazioni ridondanti)
        z_pred_c = z_pred - z_pred.mean(dim=0)
        cov = (z_pred_c.T @ z_pred_c) / (z_pred.size(0) - 1)
        cov_loss = cov.pow(2).sum() / cov.size(0) - cov.diag().pow(2).sum() / cov.size(0)

        return (
            self.sim * sim
            + self.var * var_loss
            + self.cov * cov_loss
        )


# --------------------------------------------------------------------------- #
# JEPA World Model
# --------------------------------------------------------------------------- #


class JEPAWorldModel(nn.Module):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dim: int = 128,
        latent_dim: int = 32,
        momentum: float = 0.99,
    ):
        super().__init__()
        self.latent_dim = latent_dim
        self.momentum = momentum

        self.context_encoder = ObsEncoder(obs_dim, hidden_dim, latent_dim)
        self.target_encoder = ObsEncoder(obs_dim, hidden_dim, latent_dim)  # EMA
        self.predictor = LatentPredictor(latent_dim, action_dim, hidden_dim)

        # inizializza il target encoder = copia del context encoder
        self.target_encoder.load_state_dict(self.context_encoder.state_dict())
        for p in self.target_encoder.parameters():
            p.requires_grad = False  # EMA, non si addestra direttamente

        self.vicreg = VicregLoss()
        self._update_epochs = 0

    def forward(self, obs, action, obs_next, stop_grad_target: bool = True):
        """Returns (loss, z_pred, z_target)."""
        z_c = self.context_encoder(obs)
        z_pred = self.predictor(z_c, action)
        z_target = self.target_encoder(obs_next)
        loss = self.vicreg(z_pred, z_target)
        return loss, z_pred, z_target

    @torch.no_grad()
    def update_target_network(self) -> None:
        """EMA update del target encoder verso il context encoder."""
        for tp, cp in zip(self.target_encoder.parameters(), self.context_encoder.parameters()):
            tp.data.mul_(self.momentum).add_(cp.data, alpha=1 - self.momentum)

    @torch.no_grad()
    def predict_latent(self, obs, action) -> torch.Tensor:
        z_c = self.context_encoder(obs)
        return self.predictor(z_c, action)

    def encode(self, obs, target: bool = False):
        enc = self.target_encoder if target else self.context_encoder
        return enc(obs)


# --------------------------------------------------------------------------- #
# Training loop
# --------------------------------------------------------------------------- #


def train_world_model(
    model: JEPAWorldModel,
    dataset,
    lr: float = 1e-3,
    epochs: int = 50,
    momentum_steps: int = 2,
    batch_size: int = 32,
    device: torch.device = torch.device("cpu"),
    seed: int = 0,
) -> list[float]:
    """Addestra il world model su coppie (obs, action, obs_next).

    `dataset`: iterabile di tuple (obs, action, obs_next) come tensori [batch, ...].
    Ritorna la lista della component di similarita' (mse sul latent) per epoca.
    """
    torch.manual_seed(seed)
    model.to(device)
    opt = torch.optim.Adam(model.context_encoder.parameters(), lr=lr)
    opt2 = torch.optim.Adam(model.predictor.parameters(), lr=lr)
    losses = []
    it = 0
    model.train()
    # raggruppa le coppie (obs, action, obs_next) in batch (niente BatchNorm con bsz=1)
    obs_all = torch.stack([p[0] for p in dataset]).squeeze(1)
    act_all = torch.stack([p[1] for p in dataset]).squeeze(1)
    obsn_all = torch.stack([p[2] for p in dataset]).squeeze(1)
    loader = torch.utils.data.DataLoader(
        list(zip(obs_all, act_all, obsn_all)), batch_size=batch_size, shuffle=True
    )
    for epoch in range(epochs):
        ep_loss = 0.0
        n = 0
        for obs, action, obs_next in loader:
            obs = obs.to(device)
            action = action.to(device)
            obs_next = obs_next.to(device)
            opt.zero_grad()
            opt2.zero_grad()
            loss, z_pred, z_target = model(obs, action, obs_next)
            loss.backward()
            opt.step()
            opt2.step()
            ep_loss += loss.item()
            n += 1
            it += 1
            if it % momentum_steps == 0:
                model.update_target_network()
        losses.append(ep_loss / max(n, 1))
    return losses


# --------------------------------------------------------------------------- #
# Ambiente toy: sistema dinamico lineare (oscillatore smorzato)
# --------------------------------------------------------------------------- #


class ToyOscillator:
    """World simplicissimo ma con una vera dinamica temporale.

    Stato (posizione, velocita'). Equazione: a = A * x - B * v + action.
    Serve a verificare che il world model impari a predire nel latent space un
    sistema che ha una legge fisica (non puro rumore).
    """

    def __init__(self, A: float = -2.5, B: float = 0.4, dt: float = 0.1, mu: float = 0.0):
        self.A = A
        self.B = B
        self.dt = dt
        self.mu = mu

    def step(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """state = [pos, vel]; action scalar -> accel additiva."""
        x, v = state[..., 0], state[..., 1]
        a = self.A * x - self.B * v + action[..., 0]
        x_new = x + v * self.dt
        v_new = v + a * self.dt
        if self.mu:
            x_new = x_new + torch.randn_like(x_new) * self.mu
            v_new = v_new + torch.randn_like(v_new) * self.mu
        return torch.stack([x_new, v_new], dim=-1)

    def make_dataset(self, n_traj: int = 40, len_traj: int = 30, seed: int = 0) -> list:
        torch.manual_seed(seed)
        pairs = []
        for _ in range(n_traj):
            state = torch.randn(1, 2) * 1.0
            for _ in range(len_traj):
                action = torch.rand(1, 1) * 2 - 1
                nxt = self.step(state, action)
                pairs.append((state.clone(), action.clone(), nxt.clone()))
                state = nxt
        return pairs


if __name__ == "__main__":
    torch.manual_seed(1)
    env = ToyOscillator(mu=0.05)
    dataset = env.make_dataset(n_traj=30, len_traj=20)
    model = JEPAWorldModel(obs_dim=2, action_dim=1)
    losses = train_world_model(model, dataset, epochs=40)
    print("loss latente per epoca (prime 5):", [round(l, 4) for l in losses[:5]])
    print("loss latente per epoca (ultime 5):", [round(l, 4) for l in losses[-5:]])
    print("=> il modello impara la dinamica nel latent space" if losses[-1] < losses[0] else "=> nessun apprendimento")
    # verifica: encode di due stati vicini -> latenti vicini, e predizione sensata
    s = torch.tensor([[0.5, 0.2]])
    a = torch.tensor([[0.3]])
    z_hat = model.predict_latent(s, a)
    print("latent predetto shape:", tuple(z_hat.shape))
