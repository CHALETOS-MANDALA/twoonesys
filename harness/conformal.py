"""CASCADE - Integrazione: calibrazione conformal senza logprobs.

Il problema che risolve (audit p.3 di CASCADE_PROJECT.md: "La calibrazione vera
(temperature scaling, conformal) resta lavoro futuro"): le API hosted che
espongono logprobs sono la minoranza; ENI/Anthropic-style danno solo un valore
di confidenza grezzo, e confrontare punteggi grezzi con soglie scelte a caso
(ConfidenceLevel = 0.90/0.95/0.999) non ha NESSUNA garanzia di affidabilita'.

La conformal prediction e' agnostica rispetto allo score: non servono i
logprobs, serve solo uno score di non-conformita' scambiabile (piu' basso =
piu' affidabile) raccolto su un calibration set, e un quantile corretto per la
dimensione finita del campione:

    q = k-esima statistica ordinata, k = ceil((n+1)(1-alpha))
    => P(S_test <= q) >= 1-alpha  sotto scambiabilita'

Quando l'API non da' logprobs, lo score si costruisce campionando: N>=2
generazioni per prompt (temperature > 0), si clusterizza, e si usa
non-conformita' = 1 - (quota del cluster modale) [self-consistency].

Questo modulo e' UN'INTEGRAZIONE del CASCADE, non un refactor: non tocca
ne' pipeline.py ne' neurosymbolic_guard.py. Si usa ACCANTO al pipeline:

    reg = ConformalCalibrator(alpha=0.10)
    reg.fit(sample_fn, calib_prompts)          # sample_fn = API wrapper
    d = reg.decide(sample_fn(prompt))          # d.proceed -> fidati
    # oppure, sullo score di confidenza gia' emesso dal percorso neurale:
    reg = ConformalCalibrator(alpha=0.10, score_fn=lambda r: 1.0 - float(r[0]))

Avvertenze oneste:
* La garanzia e' MARGINALE e a livello di SCORE, non di correttezza della
  risposta. eval_labeled() con ground truth dice quanto lo score traccia il
  vero esito.
* Scambiabilita': calibration set e traffico live devono venire dalla stessa
  pipe; lo shift di distribuzione annulla il numero (rifit periodico).
* temperature=0 -> self-consistency degenere (stessa risposta): il sampler
  deve campionare davvero.

Dipendenze: numpy. Il campionamento sta nel chiamante (sample_fn).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import numpy as np


# --------------------------------------------------------------------------- #
# Score di non-conformita' senza logprobs
# --------------------------------------------------------------------------- #


def _token_similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """Similarita' di base: overlap normalizzato di token (nessun embedding)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return a == b
    return len(ta & tb) / float(min(len(ta), len(tb))) >= threshold


def cluster_sizes(responses: Iterable[str],
                  similar: Callable[[str, str], bool]) -> np.ndarray:
    """Clusterizza le risposte con `similar`; ritorna le taglie dei cluster."""
    sizes, reps = [], []
    for resp in responses:
        for i, rep in enumerate(reps):
            if similar(rep, resp):
                sizes[i] += 1
                break
        else:
            reps.append(resp)
            sizes.append(1)
    return np.fromiter(sizes, dtype=float, count=len(sizes))


def consistency_score(responses: Iterable[str],
                      similar: Callable[[str, str], bool] = _token_similar) -> float:
    """Self-consistency: 1 - (quota del cluster modale). Scala 0 (forte
    accordo, affidabile) -> alto (risposte sparse, inaffidabile)."""
    responses = list(responses)
    if not responses:
        return 1.0
    sizes = cluster_sizes(responses, similar)
    return float(1.0 - sizes.max() / len(responses))


def conformal_quantile(scores: Iterable[float], alpha: float) -> float:
    """Quantile con correzione finita; score lower-is-better.

    q = k-esima statistica ordinata con k = ceil((n+1)(1-a)). Verifica di
    copertura: P(S_test <= q) >= 1-a sotto scambiabilita' (split conformal,
    Lei et al. 2018).
    """
    s = np.sort(np.fromiter(scores, dtype=float))
    n = len(s)
    k = int(math.ceil((n + 1.0) * (1.0 - alpha)))
    if k <= 0:
        return -math.inf        # nessuna decisione mai respinta
    if k > n:
        return math.inf         # troppi pochi punti di calibrazione
    return float(s[k - 1])


# --------------------------------------------------------------------------- #
# Regolatore conformal
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CalibrationDecision:
    """Esito calibrato. proceed=True -> fidarsi dello score."""
    proceed: bool
    score: float
    risk: float                 # 1 - (quota di calibrazione con score <= questo)
    threshold: float
    responses: tuple = field(default=(), repr=False)


class ConformalCalibrator:
    """Livello di rischio con garanzia di copertura sopra QUALSIASI sampler.

    API del chiamante:
        reg = ConformalCalibrator(alpha=0.10)
        reg.fit(sample_fn, prompts)          # calibrazione su casi reali
        reg.decide(responses)                # decisione a runtime
        reg.eval_labeled(sample_fn, prompts, is_good)   # verifica su ground truth

    `score_fn` default = self-consistency da campioni. Inietta un'altra
    funzione (es. sullo score di confidenza neurale gia' emesso: lambda r:
    1 - r[0]) per calibrare il segnale di confidenza del percorso neurale.
    """

    def __init__(self, alpha: float = 0.10,
                 score_fn: Callable[[Iterable], float] = None,
                 similar: Callable[[str, str], bool] = _token_similar):
        self.alpha = float(alpha)
        self.similar = similar
        if score_fn is not None:
            self.score_fn = score_fn
        else:
            self.score_fn = lambda r: consistency_score(r, similar=similar)
        self.calib_scores: np.ndarray = np.array([], dtype=float)
        self.threshold: float = -math.inf

    # -- calibrazione -------------------------------------------------------- #
    def fit_from_scores(self, scores: Iterable[float]) -> "ConformalCalibrator":
        """Calibra direttamente da una lista di score (gia' calcolati)."""
        self.calib_scores = np.fromiter(scores, dtype=float)
        if len(self.calib_scores) == 0:
            raise ValueError("calibration set vuoto: servono score reali")
        self.threshold = conformal_quantile(self.calib_scores, self.alpha)
        return self

    def fit(self, sample_fn: Callable[[str], Iterable],
            prompts: Iterable[str]) -> "ConformalCalibrator":
        """Calibra campionando ogni prompt del calibration set."""
        return self.fit_from_scores(self.score_fn(sample_fn(p)) for p in prompts)

    def add_calibration(self, sample_fn: Callable[[str], Iterable],
                        prompts: Iterable[str]) -> "ConformalCalibrator":
        """Accumula altro calibration set (rifit periodico senza buttare il
        passato)."""
        extra = np.fromiter((self.score_fn(sample_fn(p)) for p in prompts),
                            dtype=float)
        self.calib_scores = np.concatenate([self.calib_scores, extra])
        self.threshold = conformal_quantile(self.calib_scores, self.alpha)
        return self

    # -- predizione ---------------------------------------------------------- #
    def threshold_for(self, alpha: float) -> float:
        """Quantile per un altro livello di rischio, senza rifit."""
        return conformal_quantile(self.calib_scores, alpha)

    def risk_of(self, score: float) -> float:
        """Rischio calibrato dello score: 1 - P(S <= score) su calibrazione."""
        return float(1.0 - np.mean(self.calib_scores <= score))

    def decide(self, responses: Optional[Iterable] = None,
               sample_fn: Optional[Callable[[str], Iterable]] = None,
               prompt: Optional[str] = None) -> CalibrationDecision:
        """Decisione a runtime. Passa `responses` (campioni osservati) OPPURE
        `sample_fn` + `prompt` (il sampler produce i campioni con la stessa
        pipe della calibrazione, come da contratto di scambiabilita')."""
        if sample_fn is not None:
            if prompt is None:
                raise ValueError("decide(sample_fn=...) richiede il prompt")
            responses = sample_fn(prompt)
        elif responses is None:
            raise ValueError("decide richiede responses oppure sample_fn+prompt")
        score = self.score_fn(responses)
        return CalibrationDecision(
            proceed=score <= self.threshold,
            score=score,
            risk=self.risk_of(score),
            threshold=self.threshold,
            responses=tuple(responses),
        )

    # -- verifica ------------------------------------------------------------ #
    def eval_labeled(self, sample_fn: Callable[[str], Iterable],
                     prompts: Iterable[str],
                     is_good: Callable[[str, tuple], bool]) -> dict:
        """Controllo su ground truth (is_good(prompt, responses) -> bool).

        score_coverage = la garanzia conformal (quota decisioni accettate,
        attesa >= 1-alpha); precision_accepted = quanto 'fidati' ha preso
        risposte corrette: il numero che conta per l'agente.
        """
        prompts = list(prompts)
        kept = np.zeros(len(prompts), dtype=bool)
        good = np.zeros(len(prompts), dtype=bool)
        for i, p in enumerate(prompts):
            d = self.decide(sample_fn=sample_fn, prompt=p)
            kept[i] = d.proceed
            good[i] = bool(is_good(p, d.responses))
        n_acc, n_good = int(kept.sum()), int(good.sum())
        return {
            "n": len(prompts),
            "alpha": self.alpha,
            "score_coverage": float(kept.mean()),
            "abstain_rate": float(1.0 - kept.mean()),
            "accuracy_overall": float(good.mean()),
            "precision_accepted": float(good[kept].mean() if n_acc else np.nan),
            "recall_among_good": float((kept & good).sum() / n_good if n_good else np.nan),
        }