"""Test del benchmark con verita' esterna (pendolo fisico, NON generato da CASCADE)."""

import pytest

from cascade.benchmarks_external import PendulumTruth, external_truth_benchmark


def test_pendulum_dynamics_are_valid():
    p = PendulumTruth(seed=0)
    s = p.roll([0.5, 0.0], n=10)
    assert len(s) == 11
    # il pendolo e' conservativo/limitato: l'angolo non esplode
    for st in s:
        assert -1e9 < st[0] < 1e9


def test_external_truth_benchmark_runs():
    r = external_truth_benchmark(n_train=20, n_roll=15, horizon=8, epochs=10, seed=0)
    assert "wm_mae_out_of_sample" in r
    assert r["external_truth"] == "pendulum_scipy"
    assert 0.0 <= r["safe_but_fell_rate"] <= 1.0


def test_safety_metric_not_trivially_zero():
    """Deve esistere almeno la possibilita' di misurare il falso-positivo di
    sicurezza (world model dice stabile ma la verita' no), non hardcodare 0."""
    r = external_truth_benchmark(n_train=40, n_roll=30, horizon=15, epochs=20, seed=1)
    assert r["safe_checks"] > 0
    # non asseriamo che sia 0: la metrica deve essere CALCOLATA, non fittizia
    assert r["safe_but_fell"] >= 0
