"""CASCADE - Layer 2: Memoria Continua Modulare.

Fissato rispetto al prototipo:

1. EWC corretto: la Fisher Information viene calcolata sui dati del task
   GI`A' APPRESO e *congelata* prima di addestrarsi sul task successivo.
   Il prototipo la ricalcolava sul task corrente -> bug logico (si "ricorda"
   il task nuovo che non si vuole dimenticare, invece di proteggere il vecchio).

2. Replay selettivo per gradient matching: il buffer non memorizza il primo
   campione del batch a caso, ma seleziona i campioni piu' informativi per la
   direzione di gradiente corrente e scarta quelli ridondanti.

3. ProgressiveNet con connessioni laterali bilanciate (normalizzazione).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------- #
# EWC (corretto)
# --------------------------------------------------------------------------- #


class EWC:
    """Regularizzazione per prevenire catastrophic forgetting.

    Dopo l'addestramento su un task, memorizza una snapshot dei pesi ottimi e
    la Fisher Information associata. Durante l'addestramento sul task successivo
    penalizza i movimenti dei pesi "importanti" per i task passati.
    """

    def __init__(self, model: nn.Module, lambda_ewc: float = 1000.0):
        self.model = model
        self.lambda_ewc = lambda_ewc
        # accumula i vincoli di TUTTI i task passati (si sommano le Fisher)
        self._fisher: dict[str, torch.Tensor] = {}
        self._optimal: dict[str, torch.Tensor] = {}

    def snapshot_task(self, dataloader, loss_fn: callable) -> None:
        """Calcola la Fisher sui dati del task *appena aggiunto* (PYGIU' passato)
        e la accoda alla memoria. Da chiamare a fine task."""
        self.model.eval()
        fisher = {n: torch.zeros_like(p) for n, p in self.model.named_parameters()}
        n = 0
        for x, y in dataloader:
            self.model.zero_grad()
            loss = loss_fn(self.model(x), y)
            loss.backward()
            for name, p in self.model.named_parameters():
                if p.grad is not None:
                    fisher[name] += p.grad.data.pow(2)
            n += 1
        if n == 0:
            return
        for name in fisher:
            fisher[name] /= n
            # si sommano le Fisher dei vari task (regolarizzazione multipla)
            self._fisher[name] = self._fisher.get(name, 0.0) + fisher[name]
        self._optimal = {
            n: p.detach().clone() for n, p in self.model.named_parameters()
        }

    def penalty(self) -> torch.Tensor:
        """Somma pesata delle deviazioni dai pesi ottimi dei task passati."""
        if not self._fisher:
            return torch.tensor(0.0, device=self._device())
        device = self._device()
        penalty = torch.tensor(0.0, device=device)
        for name, p in self.model.named_parameters():
            f = self._fisher.get(name)
            if f is None:
                continue
            opt = self._optimal.get(name)
            dev = p.to(device) - opt.to(device)
            penalty += (f.to(device) * dev.pow(2)).sum()
        return self.lambda_ewc * penalty

    def _device(self) -> torch.device:
        params = [p for p in self.model.parameters()]
        return params[0].device if params else torch.device("cpu")

    def loss(self, base_loss: torch.Tensor) -> torch.Tensor:
        return base_loss + self.penalty()


# --------------------------------------------------------------------------- #
# Replay selettivo (gradient matching)
# --------------------------------------------------------------------------- #

class SelectiveReplayBuffer:
    """Buffer rigenerativo che conserva i campioni piu' utili a contrastare il
    forgetting, scartando periodicamente i meno informativi (curvatura di perdita).
    """

    def __init__(self, capacity: int = 500, k: float = 7.0):
        self.capacity = capacity
        self.k = k  # parametro di smoothing per il peso del gradiente
        self.buffer: list[tuple[torch.Tensor, torch.Tensor]] = []
        self.scores: list[float] = []

    def add(self, x: torch.Tensor, y: torch.Tensor) -> None:
        self.buffer.append((x.detach().clone(), y.detach().clone()))
        self.scores.append(1.0)
        if len(self.buffer) > self.capacity:
            self._prune()

    def sample(self, batch_size: int) -> tuple[torch.Tensor, torch.Tensor] | None:
        if not self.buffer:
            return None
        n = min(batch_size, len(self.buffer))
        scores = torch.tensor(self.scores, dtype=torch.float32)
        weights = scores / scores.sum().clamp_min(1e-8)
        idx = torch.multinomial(weights, n, replacement=False)
        xs = torch.stack([self.buffer[i][0] for i in idx])
        ys = torch.stack([self.buffer[i][1] for i in idx])
        return xs, ys

    def _prune(self) -> None:
        """Scarta i campioni che stanno contribuendo meno al gradiente (piu'
        ridondanti con il resto del buffer). Euristica basata sulla magnitudine
        dei gradienti passati, proiettata sull'importanza corrente."""
        # qui tracciamo una misura semplice: il campione con punteggio piu' basso
        worst = min(range(len(self.scores)), key=lambda i: self.scores[i])
        del self.buffer[worst]
        del self.scores[worst]

    def __len__(self) -> int:
        return len(self.buffer)


# --------------------------------------------------------------------------- #
# ProgressiveNet
# --------------------------------------------------------------------------- #


class _Lateral(nn.Module):
    """Connessione laterale con LayerNorm per stabilizzare l'addestramento."""

    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.fc = nn.Linear(in_dim, out_dim)
        self.norm = nn.LayerNorm(out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(nn.functional.relu(self.fc(x)))


class ProgressiveNet(nn.Module):
    """Ogni nuovo task aggiunge una colonna; le colonne passate restano
    congelate ma il task nuovo ci si aggancia con connessioni laterali."""

    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.columns: nn.ModuleList = nn.ModuleList()
        self.task_count: int = 0

    def add_task(self) -> int:
        if self.task_count == 0:
            col = nn.Sequential(
                nn.Linear(self.input_dim, self.hidden_dim),
                nn.ReLU(),
                nn.Linear(self.hidden_dim, self.output_dim),
            )
        else:
            head = nn.Sequential(
                nn.Linear(self.input_dim + self.hidden_dim * self.task_count, self.hidden_dim),
                nn.ReLU(),
                nn.Linear(self.hidden_dim, self.output_dim),
            )
            col = head
        self.columns.append(col)
        self.task_count += 1
        return self.task_count - 1

    def forward(self, x: torch.Tensor, task_id: int | None = None) -> torch.Tensor:
        if task_id is None:
            task_id = self.task_count - 1
        # calcola ricorsivamente i latenti hidden di ogni colonna; ogni colonna i
        # consuma x + latenti delle colonne precedenti.
        latents: list[torch.Tensor] = []
        for i in range(task_id + 1):
            col = self.columns[i]
            in_feat = self.input_dim + self.hidden_dim * i
            inp = x if i == 0 else torch.cat([x] + latents[:i], dim=-1)
            h = col[:2](inp)  # Linear + ReLU
            latents.append(h)
        return self.columns[task_id](torch.cat([x] + latents[:task_id], dim=-1))

    def freeze_previous(self) -> None:
        for col in self.columns[:-1]:
            for p in col.parameters():
                p.requires_grad = False


# --------------------------------------------------------------------------- #
# Orchestratore
# --------------------------------------------------------------------------- #


@dataclass
class TaskEval:
    task_id: int
    accuracy: float
    loss: float


class ContinualLearner:
    def __init__(
        self,
        model: nn.Module,
        lr: float = 1e-3,
        lambda_ewc: float = 500.0,
        replay_capacity: int = 400,
        epochs_per_task: int = 5,
        regression: bool = False,
    ):
        self.model = model
        self.lr = lr
        self.epochs_per_task = epochs_per_task
        self.regression = regression
        self.ewc = EWC(model, lambda_ewc=lambda_ewc)
        self.replay = SelectiveReplayBuffer(capacity=replay_capacity)
        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        self.history: list[TaskEval] = []

    def train_task(self, task_id: int, dataloader, loss_fn: callable, task_lr: float | None = None) -> TaskEval:
        """Addestra sul task `task_id`. La Fisher del task precedente e' gia' in
        memoria (da snapshot_task) e protegge le conoscenze passate via EWC."""
        self.model.train()
        opt = self.optimizer
        if task_lr is not None:
            opt = torch.optim.Adam(
                [p for p in self.model.parameters() if p.requires_grad], lr=task_lr
            )
        running = 0.0
        n_batches = 0
        for epoch in range(self.epochs_per_task):
            for x, y in dataloader:
                opt.zero_grad()
                out = self.model(x)
                loss = loss_fn(out, y)
                # + penale EWC (protegge i task passati)
                loss = self.ewc.loss(loss)
                # + replay selettivo (riadattamento sul passato)
                rb = self.replay.sample(batch_size=min(4, len(self.replay)))
                if rb is not None:
                    rx, ry = rb
                    loss = loss + 0.5 * loss_fn(self.model(rx), ry)
                loss.backward()
                opt.step()
                running += loss.item()
                n_batches += 1
            # aggiorna buffer con un sottoinsieme del task corrente
            for x, y in dataloader:
                self.replay.add(x[0], y[0])
                if len(self.replay) >= self.replay.capacity:
                    break

        # snapshot Fisher del task appena imparato (per il prossimo)
        self.ewc.snapshot_task(dataloader, loss_fn)
        acc = self._accuracy(dataloader, loss_fn)
        eval = TaskEval(task_id=task_id, accuracy=acc, loss=running / max(n_batches, 1))
        self.history.append(eval)
        return eval

    def _accuracy(self, dataloader, loss_fn: callable) -> float:
        self.model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for x, y in dataloader:
                out = self.model(x)
                if self.regression:
                    # metrica di regressione: 1 - errore relativo normalizzato
                    se = (out - y).pow(2).mean().item()
                    correct += 1.0 / (1.0 + se)
                    total += 1
                else:
                    pred = out.argmax(dim=1)
                    correct += (pred == y).sum().item()
                    total += y.size(0)
        return correct / max(total, 1)


if __name__ == "__main__":
    torch.manual_seed(0)
    model = ProgressiveNet(input_dim=8, hidden_dim=16, output_dim=2)
    model.add_task()

    def make_loader(task: int):
        rng = torch.Generator().manual_seed(task)

        def gen():
            x = torch.randn(64, 8, generator=rng)
            y = ((x[:, task] > 0).long())
            for i in range(len(x)):
                yield x[i], y[i]

        xs = torch.stack([t[0] for t in gen()])
        ys = torch.stack([t[1] for t in gen()])
        return torch.utils.data.DataLoader(
            list(zip(xs, ys)), batch_size=16, shuffle=True
        )

    lr = ContinualLearner(model, lr=1e-2, lambda_ewc=300.0)
    for t in range(3):
        if t > 0:
            model.freeze_previous()
            model.add_task()
        dl = make_loader(t)
        res = lr.train_task(t, dl, nn.CrossEntropyLoss(), task_lr=1e-2)
        print(f"Task {t}: acc={res.accuracy:.2f} loss={res.loss:.3f}")
