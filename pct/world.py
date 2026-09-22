"""Mondo sintetico a verita' nota per l'esperimento PCT (carta rev. 3, §9).

Deterministico: stesso seed -> stesso stream. Nessuna dipendenza oltre numpy.

Correzioni dopo l'audit del banco (difetti trovati eseguendo, non leggendo):

  CATASTROPHE  prima a2 non era MAI l'azione ottima apparente, quindi la policy
               la evitava comunque e il meccanismo "evento raro esclude l'azione"
               non aveva modo di dimostrarsi. Ora negli stati marcati a2 ha il
               tasso di successo PIU' ALTO -- sembra la scelta giusta -- e la
               catastrofe colpisce SOLO i casi difficili (d=1). Chi non sa
               condizionare vede il danno diluito su meta' popolazione.

  DELAY        prima ribaltava l'esito con probabilita' fissa uguale per tutte
               le azioni: rumore simmetrico, non credit assignment. Ora esiste
               un ORIZZONTE dichiarato: a1 riesce piu' spesso nell'immediato e
               peggio a T+N. Misurare a T+0 sceglie l'azione sbagliata.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

import numpy as np

N_C: Final = 8          # classi d'errore
N_W: Final = 4          # worker
N_STATES: Final = N_C * N_W
N_ACTIONS: Final = 3    # a0, a1, a2
A_CATASTROPHIC: Final = 2
A_DELAYED: Final = 1    # l'azione con danno differito

MAG_SUCCESS: Final = 1.0
MAG_FAILURE: Final = -1.0
MAG_CATASTROPHE: Final = -1000.0

ELIGIBLE_FOR_EXECUTION: Final = (0, 1, 2)
ELIGIBLE_FOR_EXPLORATION: Final = (0, 1)   # a2 non e' esplorabile (carta §7.1)

STATE_FUNCTION_DIGEST: Final = "stato=(classe,worker)/v1"
OUTCOME_CONTRACT_IMMEDIATO: Final = "cifre/v1@T+0"
OUTCOME_CONTRACT_ORIZZONTE: Final = "cifre/v1@T+N"


@dataclass(frozen=True)
class WorldConfig:
    seed: int = 0
    n_episodes: int = 100_000

    drift: bool = False
    catastrophe: bool = False
    confound: bool = False
    effect_flip: bool = False
    sparse: bool = False
    low_support: bool = False
    env_change: bool = False
    delay: bool = False

    p_difficult: float = 0.5
    p_catastrophe: float = 0.020        # solo sui fallimenti di a2 con d=1
    a2_boost: float = 0.30              # quanto a2 sembra buona negli stati marcati
    delay_horizon: int = 5              # N dichiarato: l'esito si misura a T+N
    delay_penalty: float = 0.35         # quanto a1 peggiora passando all'orizzonte
    delay_bonus: float = 0.25           # quanto a1 sembra buona nell'immediato
    drift_at: float = 0.5
    env_change_at: float = 0.6
    low_support_p: float = 0.995
    sparse_share: float = 0.25
    sparse_weight: float = 0.02

    def __post_init__(self) -> None:
        if self.n_episodes <= 0:
            raise ValueError("n_episodes deve essere positivo")
        if not 0.0 < self.p_difficult < 1.0:
            raise ValueError("p_difficult deve stare in (0,1)")
        if not 0.0 < self.low_support_p < 1.0:
            raise ValueError("low_support_p deve stare in (0,1)")
        if self.delay_horizon < 1:
            raise ValueError("delay_horizon deve essere >= 1")


@dataclass(frozen=True)
class Episodes:
    """Il record della carta §10.1, in forma di array paralleli."""

    state: np.ndarray            # state_key
    d: np.ndarray                # conditions.d
    e: np.ndarray                # conditions.e
    action: np.ndarray
    prop: np.ndarray             # selection_prob
    eligible: np.ndarray         # eligible_actions
    success: np.ndarray          # outcome, secondo outcome_contract
    magnitude: np.ndarray        # outcome_magnitude
    t: np.ndarray                # conditions.t
    ledger_ref: np.ndarray       # puntatore di rebuild (indice nel libro mastro)
    state_function_digest: str = STATE_FUNCTION_DIGEST
    outcome_contract: str = OUTCOME_CONTRACT_IMMEDIATO

    def __len__(self) -> int:
        return int(self.state.shape[0])

    def slice(self, start: int, stop: int) -> "Episodes":
        sl = slice(start, stop)
        return Episodes(
            state=self.state[sl], d=self.d[sl], e=self.e[sl], action=self.action[sl],
            prop=self.prop[sl], eligible=self.eligible[sl], success=self.success[sl],
            magnitude=self.magnitude[sl], t=self.t[sl], ledger_ref=self.ledger_ref[sl],
            state_function_digest=self.state_function_digest,
            outcome_contract=self.outcome_contract)

    def take(self, idx: np.ndarray) -> "Episodes":
        return Episodes(
            state=self.state[idx], d=self.d[idx], e=self.e[idx],
            action=self.action[idx], prop=self.prop[idx], eligible=self.eligible[idx],
            success=self.success[idx], magnitude=self.magnitude[idx], t=self.t[idx],
            ledger_ref=self.ledger_ref[idx],
            state_function_digest=self.state_function_digest,
            outcome_contract=self.outcome_contract)


class World:
    """Il mondo sintetico. La verita' e' `p_success`, nota per costruzione."""

    def __init__(self, cfg: WorldConfig) -> None:
        self.cfg = cfg
        rng = np.random.default_rng(cfg.seed)

        self._p_base = rng.uniform(0.20, 0.70, size=(N_STATES, N_ACTIONS, 2))

        # stati in cui a2 puo' essere catastrofica: li' a2 e' resa APPARENTEMENTE
        # la migliore, cosi' il meccanismo dell'evento raro ha qualcosa da fare
        self._catastrophic_states = rng.random(N_STATES) < 0.25
        if cfg.catastrophe:
            # a2 diventa l'azione APPARENTEMENTE migliore, ma il tetto a 0.70
            # evita il troncamento a 0.98 quando d=0: senza questo tetto la
            # difficolta' cambierebbe l'effetto RELATIVO per un artefatto di
            # clipping, e il criterio sulla media ammetterebbe d "per caso" --
            # mascherando il fatto che su una coda pesante non ci riuscirebbe.
            marc = self._catastrophic_states
            self._p_base[marc, A_CATASTROPHIC, :] = np.minimum(
                self._p_base[marc].max(axis=1) + cfg.a2_boost, 0.70)

        if cfg.effect_flip:
            self._flip_states = rng.random(N_STATES) < 0.5
            flipped = self._p_base[:, ::-1, 1]
            self._p_base[self._flip_states, :, 1] = flipped[self._flip_states]
        else:
            self._flip_states = np.zeros(N_STATES, dtype=bool)

        self._p_drift = self._p_base.copy()
        self._drift_states = rng.random(N_STATES) < 0.35
        shift = rng.uniform(-0.30, 0.30, size=(N_STATES, N_ACTIONS, 2))
        self._p_drift[self._drift_states] = np.clip(
            self._p_base[self._drift_states] + shift[self._drift_states], 0.02, 0.98)

        self._low_support_states = rng.random(N_STATES) < 0.25
        self._preferred = rng.integers(0, N_ACTIONS, size=N_STATES)

        w = np.ones(N_STATES)
        if cfg.sparse:
            rare = rng.random(N_STATES) < cfg.sparse_share
            w[rare] = cfg.sparse_weight
        self._state_p = w / w.sum()

    # ------------------------------------------------------------------ verita'

    def p_success(self, state, action, d, e, t, horizon: bool = True):
        """P(successo) vera. `horizon=False` da' l'esito immediato (T+0)."""
        p = self._p_base[state, action, e]
        if self.cfg.drift:
            t0 = int(self.cfg.drift_at * self.cfg.n_episodes)
            p = np.where(t >= t0, self._p_drift[state, action, e], p)
        p = p + 0.25 * (1.0 - 2.0 * d)
        if self.cfg.delay:
            su_a1 = action == A_DELAYED
            # a1 sembra migliore subito e peggiora all'orizzonte: credit assignment
            p = np.where(su_a1,
                         p + (self.cfg.delay_bonus if not horizon
                              else -self.cfg.delay_penalty), p)
        return np.clip(p, 0.02, 0.98)

    def true_value(self, state, action, d, e, t, horizon: bool = True):
        p = self.p_success(state, action, d, e, t, horizon=horizon)
        v = p * MAG_SUCCESS + (1.0 - p) * MAG_FAILURE
        if self.cfg.catastrophe:
            # la catastrofe colpisce SOLO i casi difficili: chi non condiziona
            # su d vede il danno diluito su meta' della popolazione
            cat = ((action == A_CATASTROPHIC) & self._catastrophic_states[state]
                   & (d == 1))
            q = self.cfg.p_catastrophe
            v_cat = (p * MAG_SUCCESS
                     + (1.0 - p) * ((1.0 - q) * MAG_FAILURE + q * MAG_CATASTROPHE))
            v = np.where(cat, v_cat, v)
        return v

    def marginal_true_value(self, state: int, action: int, e: int, t: int) -> float:
        pd = self.cfg.p_difficult
        out = 0.0
        for d_val, w in ((0, 1.0 - pd), (1, pd)):
            out += w * float(self.true_value(
                np.array([state]), np.array([action]),
                np.array([d_val]), np.array([e]), np.array([t]))[0])
        return out

    # ------------------------------------------------------- politica di comportamento

    def behaviour_probs(self, state: np.ndarray, d: np.ndarray) -> np.ndarray:
        n = state.shape[0]
        probs = np.full((n, N_ACTIONS), 1.0 / N_ACTIONS)

        if self.cfg.confound:
            pref = self._preferred[state]
            boosted = np.full((n, N_ACTIONS), 0.10)
            boosted[np.arange(n), pref] = 0.80
            probs = np.where((d == 0)[:, None], boosted, probs)

        if self.cfg.low_support:
            poor = self._low_support_states[state]
            if poor.any():
                pref = self._preferred[state]
                rest = (1.0 - self.cfg.low_support_p) / (N_ACTIONS - 1)
                forced = np.full((n, N_ACTIONS), rest)
                forced[np.arange(n), pref] = self.cfg.low_support_p
                probs = np.where(poor[:, None], forced, probs)

        return probs / probs.sum(axis=1, keepdims=True)

    # ------------------------------------------------------------------ generazione

    def generate(self) -> Episodes:
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed + 1)
        n = cfg.n_episodes

        t = np.arange(n)
        state = rng.choice(N_STATES, size=n, p=self._state_p)
        d = (rng.random(n) < cfg.p_difficult).astype(np.int64)

        e = np.zeros(n, dtype=np.int64)
        if cfg.effect_flip:
            e = (rng.random(n) < 0.5).astype(np.int64)
        if cfg.env_change:
            e = np.zeros(n, dtype=np.int64)
            e[t >= int(cfg.env_change_at * n)] = 1

        probs = self.behaviour_probs(state, d)
        u = rng.random(n)
        action = np.clip((u[:, None] > np.cumsum(probs, axis=1)).sum(axis=1),
                         0, N_ACTIONS - 1)
        prop = probs[np.arange(n), action]

        eligible = np.ones((n, N_ACTIONS), dtype=bool)

        # l'esito registrato e' quello a ORIZZONTE, come dichiara outcome_contract
        p = self.p_success(state, action, d, e, t, horizon=True)
        success = rng.random(n) < p
        magnitude = np.where(success, MAG_SUCCESS, MAG_FAILURE)

        if cfg.catastrophe:
            cat_possible = ((action == A_CATASTROPHIC)
                            & self._catastrophic_states[state] & (d == 1))
            hit = cat_possible & (~success) & (rng.random(n) < cfg.p_catastrophe)
            magnitude = np.where(hit, MAG_CATASTROPHE, magnitude)

        return Episodes(
            state=state, d=d, e=e, action=action, prop=prop, eligible=eligible,
            success=success, magnitude=magnitude.astype(np.float64), t=t,
            ledger_ref=t.copy(),
            outcome_contract=(OUTCOME_CONTRACT_ORIZZONTE if cfg.delay
                              else OUTCOME_CONTRACT_IMMEDIATO))


def with_only(phenomenon: str | None, **kwargs) -> WorldConfig:
    """Config con un solo fenomeno acceso (carta §9: uno alla volta)."""
    base = WorldConfig(**kwargs)
    if phenomenon is None:
        return base
    if not hasattr(base, phenomenon):
        raise ValueError(f"fenomeno sconosciuto: {phenomenon}")
    return replace(base, **{phenomenon: True})
