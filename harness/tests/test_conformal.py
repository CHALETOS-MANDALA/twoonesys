"""Integrazione: calibrazione conformal senza logprobs (cascade/conformal.py).

Verifica che la soglia di affidabilita' sia scelta dai dati con una copertura
garantita, NON da una soglia scelta a caso. Nessun logprob: lo score viene dal
campionamento (self-consistency) o dal segnale di confidenza neurale.
"""

import numpy as np

from cascade.conformal import (
    CalibrationDecision,
    ConformalCalibrator,
    consistency_score,
    conformal_quantile,
)


# --------------------------------------------------------------------------- #
# Score & quantile
# --------------------------------------------------------------------------- #

def test_consistency_score_agreement_is_low():
    assert consistency_score(["ok"] * 7) == 0.0


def test_consistency_score_scatter_is_high():
    replies = ["a", "b", "c", "d", "e", "f", "g", "h"]
    assert consistency_score(replies) > 0.8


def test_consistency_semantic_cluster():
    # varianti testuali della stessa risposta devono clusterizzare
    replies = ["azione ridotta", "azione ridotta subito", "azione ridotta ora",
               "reparto in tilt", "reparto in tilt totale", "x", "y", "z"]
    assert consistency_score(replies) <= 0.625


def test_conformal_quantile_finite_sample():
    scores = np.arange(1, 101, dtype=float)     # n = 100
    # k = ceil((n+1)(1-alpha)) -> k-esima statistica ordinata
    assert conformal_quantile(scores, 0.10) == 91.0
    assert conformal_quantile(scores, 0.20) == 81.0
    assert conformal_quantile(scores, 0.05) == 96.0
    # casi limite: alpha=1 -> mai respingere; alpha=0 -> impossibile con n punti
    assert conformal_quantile(scores, 1.0) == -np.inf
    assert conformal_quantile(scores, 0.0) == np.inf


# --------------------------------------------------------------------------- #
# Regolatore su score da sampling (nessun logprob)
# --------------------------------------------------------------------------- #

def _noisy_source(rate: float):
    """API sintetica: col rate `rate` produce un cluster identico (corretto),
    altrimenti risposte tutte diverse (inaffidabile). Nessun logprob."""
    rng = np.random.default_rng(42)

    def sample_fn(prompt):
        if rng.random() < rate:
            return ["OK"] * 8
        return [f"no-{j}" for j in range(8)]

    def is_good(prompt, responses):
        return responses[0] == "OK"

    return sample_fn, is_good


def test_calibrator_guarantees_coverage_on_sampling_score():
    rate = 0.91
    sample_fn, _ = _noisy_source(rate)
    reg = ConformalCalibrator(alpha=0.10).fit(sample_fn, [f"q{i}" for i in range(800)])
    test = [f"t{i}" for i in range(4000)]
    covered = sum(1 for p in test if reg.decide(
        sample_fn=sample_fn, prompt=p).proceed) / len(test)
    # garanzia conformal: copertura sullo score >= 1-alpha
    assert covered >= 1.0 - reg.alpha - 0.02


def test_calibrator_precision_on_known_label():
    rate = 0.91
    sample_fn, is_good = _noisy_source(rate)
    reg = ConformalCalibrator(alpha=0.10).fit(sample_fn, [f"q{i}" for i in range(800)])
    test = [f"t{i}" for i in range(4000)]
    rep = reg.eval_labeled(sample_fn, test, is_good)
    # quando lo score traccia il ground truth, 'fidati' -> quasi sempre giusto
    assert rep["precision_accepted"] > 1.0 - reg.alpha - 0.02
    assert rep["score_coverage"] >= 1.0 - reg.alpha - 0.02


def test_calibrator_gate_rejects_scatter_accepts_cluster():
    # con cluster corretto al 91%, il gate calibrato deve:
    #  - fidarsi di un cluster compatto (score 0)
    #  - astenersi davanti a 8 risposte tutte diverse (score alto)
    _, is_good = _noisy_source(0.91)
    reg = ConformalCalibrator(alpha=0.10).fit_from_scores([0.0] * 728 + [1.0] * 72)
    assert reg.decide(["OK"] * 8).proceed
    assert not reg.decide([f"no-{j}" for j in range(8)]).proceed
    assert not is_good("p", tuple(f"no-{j}" for j in range(8)))


def test_calibrator_risk_and_threshold_consistency():
    reg = ConformalCalibrator(
        alpha=0.20,
        score_fn=lambda replies: 1.0 - float(replies[0]),
    )
    reg.fit_from_scores([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    # k = ceil(11*0.8) = 9 -> 9° valore ordinato
    assert reg.threshold == 0.9
    # risk_of = 1 - P(S <= score): complemento della coda a livello soglia
    assert abs(reg.risk_of(0.9) - 0.1) < 1e-12
    # threshold_for con alpha diverso, senza rifit
    assert reg.threshold_for(0.50) == 0.6
    # consistenza della decisione con la soglia (soglia = 0.9 sugli score)
    assert reg.decide([0.95]).proceed        # score 0.05 <= 0.9
    assert not reg.decide([0.05]).proceed    # score 0.95 > 0.9


def test_decide_produce_clean_result():
    reg = ConformalCalibrator(alpha=0.10).fit_from_scores([0.0] * 90 + [1.0] * 10)
    d = reg.decide(["ok"] * 8)
    assert isinstance(d, CalibrationDecision)
    assert d.score == 0.0 and d.proceed
    # a soglia (score = quantile) il rischio calibrato coincide con ~alpha
    assert abs(d.risk - reg.risk_of(0.0)) < 1e-12


# --------------------------------------------------------------------------- #
# Calibrazione del segnale di confidenza neurale (ENI stile), NO logprob
# --------------------------------------------------------------------------- #

def test_calibrates_neural_confidence_signal():
    # score_fn = complemento della confidenza gia' emessa dal percorso neurale
    reg = ConformalCalibrator(
        alpha=0.10,
        score_fn=lambda replies: 1.0 - float(replies[0]),
    )
    reg.fit_from_scores([0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65])
    # k = ceil(11*0.9) = 10 -> 10° valore ordinato
    assert abs(reg.threshold - 0.65) < 1e-12
    assert reg.decide([0.9]).proceed          # conf 0.9 -> score 0.1 ok
    assert reg.decide([0.5]).proceed          # conf 0.5 -> score 0.5 <= 0.65
    assert not reg.decide([0.2]).proceed      # conf 0.2 -> score 0.8 respinto


def test_add_calibration_accumulates():
    reg = ConformalCalibrator(alpha=0.10)
    reg.fit_from_scores([0.0] * 90 + [1.0] * 10)
    reg.add_calibration(
        lambda p: ["sa", "sa", "sa", "sa", "sa", "sa", "sa", "sa"],
        ["x"] * 50,
    )
    # accumulo di score 0 sposta la soglia verso il basso => meno falsi rifiuti
    assert len(reg.calib_scores) == 150
    assert reg.risk_of(1.0) <= 0.12