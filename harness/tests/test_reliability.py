"""Integrazione: il misuratore di affidabilita' (cascade/reliability.py).

Il test centrale: un agente DICHIARA 0.96 ma il mondo risponde con molto
meno -> la curva misurata deve correggere il numero e l'ECE deve calare.
Niente LLM, niente logprob: solo la storia degli esiti reali.
"""

import numpy as np

from cascade.reliability import ReliabilityMeter


def _true_success(declared: float) -> float:
    """Il mondo vero (default, ripido): la confidenza dichiarata e' GONFIATA;
    chi dichiara 0.96 in realta' riesce ~0.93."""
    return float(np.clip(0.02 + 0.95 * declared, 0.0, 1.0))


def _overstated_success(declared: float) -> float:
    """Mondo molto miscalibrato: chi dichiara 0.96 riesce ~0.73 (rango +0.23)."""
    return float(np.clip(0.35 + 0.40 * declared, 0.0, 1.0))


def _history(n: int, rng: np.random.Generator,
             world=_true_success):
    declared = rng.random(n)
    p = np.fromiter((world(c) for c in declared), dtype=float)
    outcomes = rng.random(n) < p
    return declared, outcomes


# --------------------------------------------------------------------------- #
# 1. Il numero dichiarato diventa una MISURA
# --------------------------------------------------------------------------- #

def test_measure_demotes_inflated_confidence():
    rng = np.random.default_rng(0)
    declared, outcomes = _history(6000, rng)
    meter = ReliabilityMeter(n_bins=12).record_many(declared, outcomes).fit()

    p_measured = meter.calibrate(0.96)
    # assurdo che 0.96 dichiarato valga 0.96: il mondo dice ~0.73
    assert p_measured < 0.96
    assert abs(p_measured - _true_success(0.96)) < 0.10


def test_calibrate_is_monotone():
    rng = np.random.default_rng(1)
    declared, outcomes = _history(4000, rng)
    meter = ReliabilityMeter(n_bins=10).record_many(declared, outcomes).fit()
    grid = np.linspace(0.0, 1.0, 101)
    ps = np.fromiter((meter.calibrate(x) for x in grid), dtype=float)
    # la curva e' isotonica: non deve decrescere mai
    assert np.all(np.diff(ps) >= -1e-12)


# --------------------------------------------------------------------------- #
# 2. ECE: la misura vince sulle soglie a caso
# --------------------------------------------------------------------------- #

def test_ece_drops_after_calibration():
    rng = np.random.default_rng(2)
    declared, outcomes = _history(8000, rng, world=_overstated_success)
    meter = ReliabilityMeter(n_bins=12).record_many(declared, outcomes).fit()
    raw = meter.ece(calibrated=False)
    cal = meter.ece(calibrated=True)
    assert cal < raw                     # la curva corregge il numero
    assert raw > 0.05                    # ...che prima era gonfiato


# --------------------------------------------------------------------------- #
# 3. Gate calibrato con copertura verificata su validazione
# --------------------------------------------------------------------------- #

def test_decide_coverage_on_validation():
    rng = np.random.default_rng(3)
    tr_decl, tr_out = _history(5000, rng)
    meter = ReliabilityMeter(n_bins=10).record_many(tr_decl, tr_out).fit()
    va_decl, va_out = _history(4000, rng)
    rep = meter.coverage_check(va_decl, va_out, alpha=0.10)
    # chi il misuratore accetta, nel mondo vero riesce con copertura >= 1-alpha
    assert rep["coverage_accepted"] >= 1.0 - rep["alpha"] - 0.03
    assert rep["accept_rate"] < 0.6      # il gate non e' un pass-partout


def test_calibrated_threshold_consistent_with_decide():
    rng = np.random.default_rng(4)
    declared, outcomes = _history(5000, rng)
    meter = ReliabilityMeter(n_bins=10).record_many(declared, outcomes).fit()
    alpha = 0.10
    thr = meter.calibrated_threshold(alpha)
    assert thr < 1.0                     # il gate esiste: la misura raggiunge 1-alpha
    # a soglia: misura >= 1-alpha; subito sotto: misura < 1-alpha
    ok_hi, _ = meter.decide(min(thr + 0.02, 1.0), alpha)
    ok_lo, _ = meter.decide(max(thr - 0.02, 0.0), alpha)
    assert ok_hi and not ok_lo


# --------------------------------------------------------------------------- #
# 4. Ciclo di outcome: accumulo streaming, merge, forget
# --------------------------------------------------------------------------- #

def test_outcome_loop_streaming_accumulation():
    rng = np.random.default_rng(5)
    meter = ReliabilityMeter()
    # il loop vero: un esito alla volta, quando il mondo risponde
    for c, o in zip(*_history(300, rng)):
        meter.record(float(c), bool(o))
    assert meter.size == 300
    meter.fit()
    assert len(meter.reliability_table()) == meter.n_bins
    p = meter.calibrate(0.5)
    assert 0.0 <= p <= 1.0


def test_merge_two_domains():
    rng = np.random.default_rng(6)
    d1, o1 = _history(1000, rng)
    d2, o2 = _history(1500, rng)
    a = ReliabilityMeter(n_bins=8).record_many(d1, o1)
    b = ReliabilityMeter(n_bins=8).record_many(d2, o2)
    merged = a.merge(b).fit()
    assert merged.size == 2500
    assert merged.calibrate(0.96) < 0.96


def test_forget_oldest():
    rng = np.random.default_rng(7)
    declared, outcomes = _history(500, rng)
    meter = ReliabilityMeter(min_samples=10)
    meter.record_many(declared, outcomes)
    meter.forget_oldest(300)
    assert meter.size == 200


# --------------------------------------------------------------------------- #
# 5. Comportamento senza storia e con troppa poca
# --------------------------------------------------------------------------- #

def test_no_history_is_neutral_and_safe():
    meter = ReliabilityMeter()
    assert meter.calibrate(0.9) == 0.9          # nessuna storia: identita'
    ok, p = meter.decide(0.9, alpha=0.10)
    assert ok                                    # neutrale -> fiducia conservativa
    assert meter.ece() != meter.ece()            # NaN senza fit (ecc. onesto)


def test_min_samples_falls_back_to_global_mean():
    rng = np.random.default_rng(8)
    declared, outcomes = _history(8, rng)        # troppo pochi record
    meter = ReliabilityMeter(min_samples=30).record_many(declared, outcomes).fit()
    p = meter.calibrate(0.96)
    assert abs(p - float(np.mean(outcomes))) < 1e-9


# --------------------------------------------------------------------------- #
# 6. Ponte verso il gate conformal (conformal.py)
# --------------------------------------------------------------------------- #

def test_score_of_feeds_conformal_calibrator():
    from cascade.conformal import ConformalCalibrator
    rng = np.random.default_rng(9)
    declared, outcomes = _history(5000, rng)
    meter = ReliabilityMeter(n_bins=10).record_many(declared, outcomes).fit()
    # score di non-conformita' = complemento della misura (lower = migliore)
    scores = [meter.score_of(c) for c in declared]
    assert all(0.0 <= s <= 1.0 for s in scores)
    reg = ConformalCalibrator(
        alpha=0.10, score_fn=lambda r: float(r[0]),
    ).fit_from_scores(scores)
    # con la misura buona, 'fidati' copre >= 1-alpha sugli score
    keep = np.array([reg.decide([util]).proceed for util in scores])
    assert bool(keep.mean()) >= 1.0 - reg.alpha - 0.02