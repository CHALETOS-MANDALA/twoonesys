"""CASCADE - Integrazione: il misuratore di affidabilita' (misura, non vibe).

Il problema che risolve (audit p.3 di CASCADE_PROJECT.md): la confidenza del
percorso neurale e' AUTO-DICHIARATA — `confidence = float(winner.confidence)`
arriva dall'agente e viaggia nei contratti senza mai essere stata MISURATA.
Nessuno ha mai verificato che 0.96 corrisponda al 96% di esiti riusciti.

Questo modulo e' il "contatore davanti" (il meter del System One): accumula
(cofidenza, esito reale) dal loop di outcome della memoria, e produce una
curva di affidabilita' MESSA IN ORDINE (isotonic / PAV), monotona e
smussata, che converte la confidenza dichiarata in probabilita' misurata:

    cal = ReliabilityMeter().record_many(confs, esiti).fit()
    p = cal.calibrate(0.96)      # -> 0.8 se il mondo dice che 0.96 vale ~0.8

E' UN'INTEGRAZIONE del CASCADE, non un refactor: non tocca il pipeline ne' i
layer. Si usa nel punto in cui l'ESITO e' noto — lo stesso loop in cui la
Layer 2 addestra il world model (`remember()`): il chiamante chiama
`meter.record(confidence, successo)` quando il mondo risponde.

Due metodi, due scopi (da non confondere):
* `calibrate(c)`  -> da' SIGNIFICATO al numero (0.96 = 96% misurato).
* `decide(c, a)`  -> gate calibrato: "fidati se p_misurata >= 1-a".
  Il gate con garanzia di COPERtura li' c'e' gia': e' il ConformalCalibrator
  di conformal.py, che da qui puoi alimentare con score = 1 - calibrate(c).

Avvertenze oneste:
* Serve una STORIA DI ESITI: senza label, il misuratore non esiste (conformal
  garantisce senza label; la misura no).
* Scambiabilita': se il traffico cambia, la curva invecchia — rifit (o
  dimentica i vecchi record con `forget_oldest`).
* La curva misura P(esito | confidenza dichiarata): se l'agente cambia stile,
  la relazione cambia con lui.

Dipendenze: numpy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np


# --------------------------------------------------------------------------- #
# Isotonic regression (PAV), monotona non-decrescente, con pesi
# --------------------------------------------------------------------------- #


def _pav_monotonic(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Pool-Adjacent-Violators: fit isotonico non-decrescente di `y` (con pesi
    `w`), rispettando l'ORDINE degli input (i bin sono gia' in ordine di
    confidenza). Ritorna i valori calzati, nell'ordine di ingresso."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    vals: list[float] = []
    sums: list[float] = []
    counts: list[int] = []
    for yy, ww in zip(y, w):
        vals.append(float(yy * ww))
        sums.append(float(ww))
        counts.append(1)
        while len(vals) >= 2 and vals[-1] / sums[-1] < vals[-2] / sums[-2]:
            m = (vals[-2] + vals[-1]) / (sums[-2] + sums[-1])
            vals[-2] = m * (sums[-2] + sums[-1])
            sums[-2] += sums[-1]
            counts[-2] += counts[-1]
            vals.pop()
            sums.pop()
            counts.pop()
    return np.repeat(np.asarray(vals) / np.asarray(sums), counts)


# --------------------------------------------------------------------------- #
# Misuratore
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReliabilityBin:
    lo: float
    hi: float
    count: int
    successi: int
    misurata: float        # probabilita' PAV-calibrata del bin


class ReliabilityMeter:
    """Curva di affidabilita' misurata su esiti reali.

    Accumula coppie (confidenza dichiarata 0..1, esito binario) e calza una
    curva della probabilita' di successo. Monotona e smussata (isotonic PAV),
    con pseudoconti (Laplace) per i bin vuoti -> mai overfit su una manciata
    di punti, mai un numero che esce dal range [0,1].
    """

    def __init__(self, n_bins: int = 10, prior: float = 1.0,
                 min_samples: int = 30):
        self.n_bins = int(n_bins)
        self.prior = float(prior)
        self.min_samples = int(min_samples)
        self._conf: np.ndarray = np.empty(0, dtype=float)
        self._out: np.ndarray = np.empty(0, dtype=bool)
        self._bins: list[ReliabilityBin] = []

    # -- accumulo (loop di outcome) ------------------------------------------ #
    def record(self, confidence: float, outcome: bool) -> "ReliabilityMeter":
        """Registra un esito reale per la confidenza dichiarata."""
        return self.record_many([confidence], [outcome])

    def record_many(self, confidences: Sequence[float],
                    outcomes: Sequence[bool]) -> "ReliabilityMeter":
        if len(confidences) != len(outcomes):
            raise ValueError("confidenze ed esiti devono avere la stessa lunghezza")
        c = np.clip(np.asarray(confidences, dtype=float), 0.0, 1.0)
        o = np.asarray(outcomes, dtype=bool)
        self._conf = np.concatenate([self._conf, c])
        self._out = np.concatenate([self._out, o])
        return self

    def merge(self, other: "ReliabilityMeter") -> "ReliabilityMeter":
        """Unisce un altro misuratore (es. rifit per dominio)."""
        self._conf = np.concatenate([self._conf, other._conf])
        self._out = np.concatenate([self._out, other._out])
        return self

    def forget_oldest(self, k: int) -> "ReliabilityMeter":
        """Scarta i k record piu' vecchi (la curva invecchia)."""
        if k > 0 and k < len(self._conf):
            self._conf = self._conf[k:]
            self._out = self._out[k:]
        elif k >= len(self._conf):
            self._conf = np.empty(0)
            self._out = np.empty(0)
        return self

    @property
    def size(self) -> int:
        return len(self._conf)

    # -- calibrazione --------------------------------------------------------- #
    def fit(self) -> "ReliabilityMeter":
        """Costruisce la curva dai record accumulati (idempotente)."""
        self._bins = []
        if self.size == 0:
            return self
        edges = np.linspace(0.0, 1.0, self.n_bins + 1)
        idx = np.clip(np.digitize(self._conf, edges[1:], right=False),
                      0, self.n_bins - 1)
        raw_p = np.empty(self.n_bins)
        weights = np.zeros(self.n_bins)
        fallback = float(self._out.mean())
        for b in range(self.n_bins):
            mask = idx == b
            n = int(mask.sum())
            succ = int(self._out[mask].sum())
            if n == 0:
                raw_p[b] = np.nan                 # bin vuoto: PAV lo ignora
            else:
                # Laplace (pseudoconti) anti-overfit sui bin piccoli
                raw_p[b] = (succ + self.prior) / (n + 2.0 * self.prior)
            weights[b] = n
        # i bin vuoti ereditano la media globale DOPO l'isotonia
        known = ~np.isnan(raw_p)
        if known.sum() == 0:
            fitted = np.full(self.n_bins, fallback)
        else:
            fitted = np.full(self.n_bins, fallback)
            fitted[known] = _pav_monotonic(raw_p[known], weights[known])
        for b in range(self.n_bins):
            lo, hi = edges[b], edges[b + 1]
            succ = int(self._out[idx == b].sum())
            n = int((idx == b).sum())
            self._bins.append(ReliabilityBin(
                lo=lo, hi=hi, count=n, successi=succ,
                misurata=float(fitted[b]),
            ))
        return self

    def _bin_index(self, confidence: float) -> int:
        return min(int(confidence * self.n_bins), self.n_bins - 1)

    def calibrate(self, confidence: float) -> float:
        """Confidenza dichiarata -> probabilita' di successo MISURATA.

        Prima di `fit()` (o sotto `min_samples`) ripiega su una stima global
        (media degli esiti) invece di inventare un numero.
        """
        c = float(np.clip(confidence, 0.0, 1.0))
        if self.size == 0:
            return c                              # nessuna storia: neutro
        if self.size < self.min_samples or not self._bins:
            return float(self._out.mean())        # troppi pochi record: media globale
        return self._bins[self._bin_index(c)].misurata

    def score_of(self, confidence: float) -> float:
        """Score di non-conformita' (lower = migliore) dal valore misurato:
        pronto per il ConformalCalibrator di conformal.py."""
        return float(1.0 - self.calibrate(confidence))

    def calibrated_threshold(self, alpha: float) -> float:
        """La minima confidenza dichiarata la cui misura >= 1-alpha."""
        target = 1.0 - float(alpha)
        xs = np.linspace(0.0, 1.0, max(self.n_bins * 20, 50))
        ps = np.fromiter((self.calibrate(x) for x in xs), dtype=float)
        idx = np.argmax(ps >= target)
        return float(xs[idx]) if ps.max() >= target else 1.0

    def decide(self, confidence: float, alpha: float = 0.10) -> tuple[bool, float]:
        """Gate calibrato: proceed se la misura >= (1-alpha). Ritorna la
        prob. misurata (il numero che ora significa qualcosa)."""
        p = self.calibrate(confidence)
        return float(p) >= 1.0 - float(alpha), float(p)

    # -- verifica ------------------------------------------------------------- #
    def ece(self, calibrated: bool = True) -> float:
        """Expected Calibration Error sui record gia' visti. `calibrated=True`:
        errore della curva (deve tendere a 0 su dati che la fingono); False:
        errore delle confidenze RAWL dichiarate (l'ECE della gente che usa
        soglie a caso). Il confronto misura quanto il misuratore ripaga."""
        if self.size == 0 or not self._bins:
            return float("nan")
        total = 0.0
        for b in self._bins:
            if b.count == 0:
                continue
            p_hat = float(b.misurata if calibrated else np.clip(
                (b.lo + b.hi) / 2.0, 0.0, 1.0))
            p_real = b.successi / b.count
            total += b.count * abs(p_hat - p_real)
        return float(total / self.size)

    def coverage_check(self, confidences: Sequence[float],
                       outcomes: Sequence[float], alpha: float = 0.10) -> dict:
        """Su un set di validazione labeled: quante decisioni accettate hanno
        avuto esito ok (copertura reale >= 1-alpha quando la misura funziona)."""
        c = np.clip(np.asarray(confidences, dtype=float), 0.0, 1.0)
        o = np.asarray(outcomes, dtype=bool)
        keep = np.fromiter((self.calibrate(x) >= 1.0 - alpha for x in c),
                           dtype=bool, count=len(c))
        n_keep, n_ok = int(keep.sum()), int(o.sum())
        return {
            "n": len(c),
            "alpha": float(alpha),
            "accept_rate": float(keep.mean()),
            "coverage_accepted": float(o[keep].mean() if n_keep else np.nan),
            "recall_among_ok": float((keep & o).sum() / n_ok if n_ok else np.nan),
        }

    def reliability_table(self) -> list[dict]:
        """Tabella di diagnosi (per certificato/report)."""
        return [
            {"bin": f"[{b.lo:.2f},{b.hi:.2f})", "count": b.count,
             "successi": b.successi, "misurata": round(b.misurata, 4)}
            for b in self._bins
        ]