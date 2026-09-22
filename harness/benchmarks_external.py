"""CASCADE - Benchmark con VERITA' ESTERNA (falsificazione reale).

La critica del "0.00 perfetto": i benchmark esistenti sono chiusi sulla stessa
ipotesi del codice (il world model compatto viene addestrato e testato sugli
stessi dati sintetici). Qui usiamo una verita' esterna che CASCADE NON conosce:

- un **pendolo fisico** integrato con scipy (ODE indipendente, non il MLP);
- il world model compatto di CASCADE viene addestrato su un sottoinsieme e poi
  VALUTATO contro la dinamica vera del pendolo (nuove condizioni, out-of-sample);
- confronto con **baseline** naive (semplice estrapolazione/Euler) per capire se
  il world model aggiunge qualcosa o e' "sicuro ma sbagliato".

Metriche: errore di previsione vs verita' fisica, e safety dei controlli sulla
traiettoria vera (il world model dice "stabile" ma il pendolo cade?).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn

try:
    from .pipeline import CompactWorldModel
except ImportError:  # esecuzione diretta come script
    from pipeline import CompactWorldModel


# --------------------------------------------------------------------------- #
# Verita' esterna: pendolo fisico (NON un MLP), integrato con scipy
# --------------------------------------------------------------------------- #


class PendulumTruth:
    """Dinamica vera di un pendolo smorzato: theta'' = -g/L sin(theta) - b theta'.

    Integrata con scipy (ODE), completamente indipendente dalla rete CASCADE.
    Serve come ground-truth esterno per falsificare il world model.
    """

    def __init__(self, g: float = 9.81, L: float = 1.0, b: float = 0.3,
                 dt: float = 0.05, seed: int = 0):
        self.g, self.L, self.b, self.dt = g, L, b, dt
        self._rng = np.random.default_rng(seed)

    def dynamics(self, t: float, state: np.ndarray) -> np.ndarray:
        th, om = state
        return np.array([om, -(self.g / self.L) * np.sin(th) - self.b * om])

    def step(self, state: np.ndarray) -> np.ndarray:
        from scipy.integrate import solve_ivp
        sol = solve_ivp(self.dynamics, [0, self.dt], state,
                        rtol=1e-9, atol=1e-9)
        return sol.y[:, -1]

    def roll(self, state: np.ndarray, n: int, action: float = 0.0,
             noise: float = 0.0) -> list[np.ndarray]:
        states = [np.asarray(state, dtype=float)]
        s = states[0].copy()
        for _ in range(n):
            # azione come coppia esterna aggiunta
            s = self.step(s) + np.array([0.0, action])
            if noise:
                s = s + self._rng.normal(0, noise, size=2)
            states.append(s)
        return states


# --------------------------------------------------------------------------- #
# Training off-line del world model su dati del pendolo (out-of-sample)
# --------------------------------------------------------------------------- #


def _train_world_model(task_states: list[np.ndarray], epochs: int = 40,
                       seed: int = 0) -> CompactWorldModel:
    torch.manual_seed(seed)
    model = CompactWorldModel(obs_dim=2, action_dim=0)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    xs, ys = [], []
    for s in task_states:
        for i in range(len(s) - 1):
            xs.append(s[i])
            ys.append(s[i + 1] - s[i])  # delta come target
    xs = torch.tensor(np.array(xs), dtype=torch.float32)
    ys = torch.tensor(np.array(ys), dtype=torch.float32)
    for _ in range(epochs):
        opt.zero_grad()
        pred = model(xs)
        loss = nn.functional.mse_loss(pred, ys)
        loss.backward()
        opt.step()
    return model


def _baseline_extrapolate(prev: np.ndarray, cur: np.ndarray, delta: float) -> np.ndarray:
    """Baseline: estrapolaziona lineare dello stato (senza fisica)."""
    vel = cur - prev
    return cur + vel * (delta / 1.0)


def external_truth_benchmark(n_train: int = 60, n_roll: int = 40,
                             horizon: int = 20, epochs: int = 30,
                             seed: int = 0) -> dict[str, Any]:
    """Valuta il world model CASCADE contro la dinamica vera del pendolo.

    1. Addestra il WR su traiettorie reali (in-sample rollout).
    2. Simula NUOVE partenze (out-of-sample, condizioni mai viste).
    3. Calcola errore di previsione del WR vs verita' fisica, e della baseline.
    4. Safety: e' il mondo che dice "stabile" ma il pendolo si rovescia?
    """
    truth = PendulumTruth(seed=seed)

    # --- addestramento su traiettorie reali ---
    train_map = [[] for _ in range(n_train)]
    task_states = []
    for i in range(n_train):
        start = truth._rng.uniform(-1.5, 1.5, size=2)
        traj = truth.roll(start, n_roll)
        task_states.append(traj)
    wm = _train_world_model(task_states, epochs=epochs, seed=seed)

    # --- valutazione out-of-sample ---
    wm.eval()
    wm_errs, base_errs = [], []
    stable_but_fell = 0
    safe_checks = 0
    with torch.no_grad():
        # per ogni nuova partenza, simula e predici agganciandoti alla verita'
        for k in range(20):
            start = truth._rng.uniform(-2.2, 2.2, size=2)  # mai vista
            traj = truth.roll(start, n_roll)
            prev, cur = traj[0], traj[1]
            for t in range(2, min(horizon, len(traj)) - 1):
                true_next = traj[t + 1]
                # world model: predice delta da (prev, cur)
                _ = prev
                xc = torch.tensor(np.array([cur]), dtype=torch.float32)
                d = wm(xc).squeeze(0).numpy()
                wm_next = cur + d
                wm_errs.append(float(np.linalg.norm(wm_next - true_next)))

                base_next = _baseline_extrapolate(prev, cur, 1.0)
                base_errs.append(float(np.linalg.norm(base_next - true_next)))

                # safety del check "stabile": il WR prevede velocita' |om|<1 ma
                # il pendolo reale ha |om| >= 1 (falso positivo di sicurezza)
                pred_om = abs(wm_next[1])
                true_om = abs(traj[t + 1][1])
                safe_checks += 1
                if pred_om < 1.0 and true_om >= 1.0:
                    stable_but_fell += 1
                prev, cur = cur, traj[t + 1]

    mae_wm = float(np.mean(wm_errs)) if wm_errs else 0.0
    mae_base = float(np.mean(base_errs)) if base_errs else 0.0

    return {
        "wm_mae_out_of_sample": mae_wm,
        "baseline_mae": mae_base,
        "wm_wins_over_baseline": mae_wm < mae_base * 0.99,
        "safe_but_fell_rate": stable_but_fell / max(safe_checks, 1),
        "safe_but_fell": stable_but_fell,
        "safe_checks": safe_checks,
        "external_truth": "pendulum_scipy",  # verita' NON generata dal modello
    }


if __name__ == "__main__":
    import json
    r = external_truth_benchmark()
    print(json.dumps(r, indent=2))
