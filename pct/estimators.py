"""Stimatori di valore per PCT.

Due stimatori, ed e' la loro SEPARAZIONE che il test 3 della specifica verifica:

  naive_mean   media semplice degli esiti osservati per (stato, azione).
               E' cio' che fa chiunque aggreghi senza propensione: e' distorta
               appena la politica di comportamento dipende da una variabile che
               influenza anche l'esito.

  hajek        media pesata per l'inverso della propensione (auto-normalizzata).
               Recupera il valore controfattuale marginale.

`ess` misura il supporto effettivo: e' la quantita' che fa scattare NO_EVIDENCE.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ValueEstimate:
    value: float      # stima del valore atteso della magnitudine
    ess: float        # dimensione campionaria efficace dei pesi
    n: int            # episodi grezzi nella cella
    std_err: float    # errore standard pesato


_EMPTY = ValueEstimate(value=float("nan"), ess=0.0, n=0, std_err=float("nan"))


def naive_mean(magnitude: np.ndarray) -> ValueEstimate:
    """Media semplice. Nessuna correzione: e' l'aggregato ingenuo."""
    n = int(magnitude.shape[0])
    if n == 0:
        return _EMPTY
    value = float(magnitude.mean())
    std_err = float(magnitude.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
    return ValueEstimate(value=value, ess=float(n), n=n, std_err=std_err)


def effective_sample_size(weights: np.ndarray) -> float:
    """ESS = (sum w)^2 / sum(w^2). Con pesi uguali coincide con n."""
    if weights.shape[0] == 0:
        return 0.0
    s = float(weights.sum())
    s2 = float((weights ** 2).sum())
    if s2 <= 0.0:
        return 0.0
    return (s * s) / s2


def hajek(magnitude: np.ndarray, propensity: np.ndarray) -> ValueEstimate:
    """Stimatore Hajek (IPS auto-normalizzato).

    Pesi w = 1/p. La normalizzazione per sum(w) invece che per n limita la
    varianza e mantiene la stima dentro l'intervallo delle osservazioni.
    """
    n = int(magnitude.shape[0])
    if n == 0:
        return _EMPTY
    if np.any(propensity <= 0.0):
        raise ValueError("propensita' nulla o negativa: positivita' violata")

    w = 1.0 / propensity
    sw = float(w.sum())
    value = float((w * magnitude).sum() / sw)

    ess = effective_sample_size(w)
    # varianza pesata attorno alla stima, riportata all'ESS
    var = float((w * (magnitude - value) ** 2).sum() / sw)
    std_err = float(np.sqrt(var / ess)) if ess > 0 else float("inf")

    return ValueEstimate(value=value, ess=ess, n=n, std_err=std_err)


def lower_confidence_bound(est: ValueEstimate, z: float = 1.96) -> float:
    """Limite inferiore usato dalla policy per scegliere (specifica §3.1)."""
    if est.n == 0 or not np.isfinite(est.std_err):
        return float("-inf")
    return est.value - z * est.std_err
