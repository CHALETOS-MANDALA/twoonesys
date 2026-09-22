"""La policy -- UNA sola, condivisa da tutti i bracci (spec §3).

Se questo file si comportasse diversamente a seconda del provider, l'esperimento
sarebbe nullo: la differenza misurata non sarebbe piu' attribuibile
all'informazione. Per questo la policy non conosce il nome del provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from evidence import Conditions, Evidence, EvidenceProvider, Status

Z_LCB = 1.96


@dataclass(frozen=True)
class PolicyConfig:
    safe_default: int = 0          # azione di ripiego quando non c'e' evidenza
    catastrophe_threshold: float = 100.0
    epsilon_eval: float = 0.05     # esplorazione permanente (carta §7.1)
    ess_min: float = 30.0
    z: float = Z_LCB

    def __post_init__(self) -> None:
        if not 0.0 <= self.epsilon_eval < 1.0:
            raise ValueError("epsilon_eval fuori intervallo")
        if self.catastrophe_threshold <= 0:
            raise ValueError("soglia di catastrofe non positiva")


def lcb(value_hat: float, std_err: float, z: float) -> float:
    if not np.isfinite(std_err):
        return float("-inf")
    return value_hat - z * std_err


def decide(evidence: Evidence, eligible_execution: Sequence[int],
           eligible_exploration: Sequence[int], cfg: PolicyConfig,
           rng: np.random.Generator) -> int:
    """Sceglie un'azione. E' l'UNICO punto del sistema che sceglie."""

    # 4. esplorazione permanente: solo fra le azioni ESPLORABILI (mai a2)
    if eligible_exploration and rng.random() < cfg.epsilon_eval:
        return int(rng.choice(np.asarray(eligible_exploration)))

    # 1. nessuna evidenza utilizzabile -> ripiego sicuro dichiarato
    if evidence.status is Status.NO_EVIDENCE or not evidence.per_action:
        return cfg.safe_default

    # 2. un evento raro abbastanza grave esclude l'azione: e' cio' che
    #    l'aggregato NON puo' fare, perche' la media non espone il singolo caso
    vietate = {ev.action for ev in evidence.rare_events
               if ev.magnitude <= -cfg.catastrophe_threshold}

    candidate = [a for a in eligible_execution
                 if a in evidence.per_action and a not in vietate]
    if not candidate:
        return cfg.safe_default

    # 3. argmax del limite inferiore
    best, best_score = cfg.safe_default, float("-inf")
    for a in candidate:
        ev = evidence.per_action[a]
        score = lcb(ev.value_hat, ev.std_err, cfg.z)
        if score > best_score:
            best, best_score = a, score
    return int(best)


def run_policy(provider: EvidenceProvider, states, ds, es, ts,
               eligible_execution: Sequence[int],
               eligible_exploration: Sequence[int],
               cfg: PolicyConfig, seed: int) -> np.ndarray:
    """Applica la policy a uno stream di episodi. Restituisce le azioni scelte."""
    rng = np.random.default_rng(seed)
    out = np.empty(states.shape[0], dtype=np.int64)
    for i in range(states.shape[0]):
        cond = Conditions(d=int(ds[i]), e=int(es[i]), t=int(ts[i]))
        ev = provider.query(int(states[i]), eligible_execution, cond)
        out[i] = decide(ev, eligible_execution, eligible_exploration, cfg, rng)
    return out
