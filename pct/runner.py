"""Esecuzione dell'esperimento §9: tre fold, quattro bracci, confronto appaiato.

I bracci decidono sugli STESSI episodi, con lo stesso seed di esplorazione:
si misura la differenza per episodio e si fa bootstrap sulle differenze
(spec §4.2). E' cio' che rende l'esperimento economico.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from evidence_agg import AggregateProvider
from evidence_param import ParametricProvider
from evidence_prec import PrecedentProvider
from policy import PolicyConfig, run_policy
from structure import learn_structure_stable
from world import (A_CATASTROPHIC, ELIGIBLE_FOR_EXECUTION,
                   ELIGIBLE_FOR_EXPLORATION, N_ACTIONS, Episodes, World,
                   with_only)

FOLD_STRUTTURA = 0.40
FOLD_STIMA = 0.80


@dataclass(frozen=True)
class ArmResult:
    name: str
    regret_mean: float
    regret_per_episode: np.ndarray
    catastrophe_expected: float
    no_evidence_rate: float
    build_seconds: float
    query_seconds: float
    bytes_retained: int


@dataclass(frozen=True)
class Comparison:
    phenomenon: str
    arms: dict[str, ArmResult]
    paired: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    cond_d: float = 0.0   # quota di stati in cui la struttura ha ammesso d
    cond_e: float = 0.0   # idem per e


def _folds(ep: Episodes) -> tuple[Episodes, Episodes, Episodes]:
    n = len(ep)
    a, b = int(FOLD_STRUTTURA * n), int(FOLD_STIMA * n)
    return ep.slice(0, a), ep.slice(a, b), ep.slice(b, n)


def _regret(w: World, ep: Episodes, chosen: np.ndarray) -> np.ndarray:
    """rimpianto = valore dell'azione ottima vera - valore dell'azione scelta."""
    valori = np.stack([
        w.true_value(ep.state, np.full(len(ep), a), ep.d, ep.e, ep.t)
        for a in range(N_ACTIONS)])
    ottimo = valori.max(axis=0)
    scelto = valori[chosen, np.arange(len(ep))]
    return ottimo - scelto


def _catastrofi_attese(w: World, ep: Episodes, chosen: np.ndarray) -> float:
    if not w.cfg.catastrophe:
        return 0.0
    marcati = w._catastrophic_states[ep.state]
    su_a2 = chosen == A_CATASTROPHIC
    p = w.p_success(ep.state, chosen, ep.d, ep.e, ep.t)
    return float(((1.0 - p) * w.cfg.p_catastrophe * (marcati & su_a2)).sum())


def _no_evidence_rate(provider, ep: Episodes) -> float:
    from evidence import Conditions, Status
    n = min(len(ep), 3_000)
    vuoti = 0
    for i in range(n):
        c = Conditions(d=int(ep.d[i]), e=int(ep.e[i]), t=int(ep.t[i]))
        if provider.query(int(ep.state[i]), ELIGIBLE_FOR_EXECUTION,
                          c).status is Status.NO_EVIDENCE:
            vuoti += 1
    return vuoti / n


def _bytes_retained(provider) -> int:
    """Ledger dei costi (spec §10.1): quanto costa conservare."""
    if isinstance(provider, PrecedentProvider):
        ep = provider._ep
        # stato,d,e,azione,t (int64) + prop,magnitudine (float64) = 7 campi
        return len(ep) * 7 * 8
    if isinstance(provider, AggregateProvider):
        return len(provider._table) * 4 * 8
    if isinstance(provider, ParametricProvider):
        return sum(b.nbytes for b in provider._beta.values())
    return 0


def run_phenomenon(phenomenon: str | None, seed: int = 101,
                   n_episodes: int = 200_000,
                   cfg_policy: PolicyConfig | None = None,
                   n_boot_struttura: int = 12) -> Comparison:
    cfg_policy = cfg_policy or PolicyConfig()
    wcfg = with_only(phenomenon, seed=seed, n_episodes=n_episodes)
    w = World(wcfg)
    ep = w.generate()
    struttura, stima, valutazione = _folds(ep)
    # il fold di struttura decide QUALI condizioni meritano di essere usate,
    # e viene congelato prima che si stimi qualunque valore (carta §4.5)
    st = learn_structure_stable(struttura, n_boot=n_boot_struttura,
                                seed=seed)

    costruttori: dict[str, Callable[[Episodes], object]] = {
        "A_aggregato": lambda e: AggregateProvider(e, ess_min=cfg_policy.ess_min),
        "C_parametrico": lambda e: ParametricProvider(e, ess_min=cfg_policy.ess_min),
        "B_pct": lambda e: PrecedentProvider(
            e, structure=st, ess_min=cfg_policy.ess_min,
            rare_threshold=cfg_policy.catastrophe_threshold),
    }

    arms: dict[str, ArmResult] = {}

    # braccio di controllo: nessuna informazione (P0)
    niente = np.full(len(valutazione), cfg_policy.safe_default, dtype=np.int64)
    arms["P0_niente"] = ArmResult(
        name="P0_niente", regret_mean=float(_regret(w, valutazione, niente).mean()),
        regret_per_episode=_regret(w, valutazione, niente),
        catastrophe_expected=_catastrofi_attese(w, valutazione, niente),
        no_evidence_rate=1.0, build_seconds=0.0, query_seconds=0.0,
        bytes_retained=0)

    for name, build in costruttori.items():
        t0 = time.perf_counter()
        provider = build(stima)
        t_build = time.perf_counter() - t0

        t0 = time.perf_counter()
        scelte = run_policy(provider, valutazione.state, valutazione.d,
                            valutazione.e, valutazione.t,
                            ELIGIBLE_FOR_EXECUTION, ELIGIBLE_FOR_EXPLORATION,
                            cfg_policy, seed=seed + 999)
        t_query = time.perf_counter() - t0

        reg = _regret(w, valutazione, scelte)
        arms[name] = ArmResult(
            name=name, regret_mean=float(reg.mean()), regret_per_episode=reg,
            catastrophe_expected=_catastrofi_attese(w, valutazione, scelte),
            no_evidence_rate=_no_evidence_rate(provider, valutazione),
            build_seconds=t_build, query_seconds=t_query,
            bytes_retained=_bytes_retained(provider))

    paired = {}
    for altro in ("A_aggregato", "C_parametrico", "P0_niente"):
        paired[f"B_vs_{altro}"] = paired_bootstrap(
            arms["B_pct"].regret_per_episode, arms[altro].regret_per_episode,
            seed=seed)

    return Comparison(phenomenon=phenomenon or "nessuno", arms=arms, paired=paired,
                      cond_d=float(st.use_d.mean()), cond_e=float(st.use_e.mean()))


def paired_bootstrap(a: np.ndarray, b: np.ndarray, n_boot: int = 2_000,
                     seed: int = 0) -> tuple[float, float, float]:
    """Differenza media (a - b) con IC95 bootstrap sulle differenze appaiate.

    Negativo = `a` ha meno rimpianto, cioe' e' migliore.
    """
    if a.shape != b.shape:
        raise ValueError("i bracci devono decidere sugli stessi episodi")
    diff = a - b
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, diff.shape[0], size=(n_boot, diff.shape[0]))
    campioni = diff[idx].mean(axis=1)
    return (float(diff.mean()), float(np.percentile(campioni, 2.5)),
            float(np.percentile(campioni, 97.5)))
