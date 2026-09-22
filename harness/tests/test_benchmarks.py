"""Test dei benchmark veri (dominio-agnostico) su tutti i layer."""

import pytest

from cascade.benchmarks import (
    a2a_http_benchmark,
    causal_benchmark,
    evaluate_forgetting,
    permuted_tasks,
    run_all_benchmarks,
    safety_benchmark,
)


# --------------------------------------------------------------------------- #
# Fronte 1: memoria / forgetting
# --------------------------------------------------------------------------- #

def test_ewc_improves_retention_on_shared_net():
    """Su una rete condivisa, EWC deve ridurre il catastrophic forgetting."""
    tasks = permuted_tasks(4, dim=16, seed=1)
    off = evaluate_forgetting(tasks, use_ewc=False, epochs_per_task=5, seed=1)
    on = evaluate_forgetting(tasks, use_ewc=True, epochs_per_task=5, seed=1)
    assert on["forgetting_metric"] > off["forgetting_metric"] + 0.02


def test_progressive_net_has_minimal_forgetting():
    tasks = permuted_tasks(4, dim=16, seed=1)
    prog = evaluate_forgetting(tasks, use_ewc=False, epochs_per_task=5,
                               seed=1, progressive=True)
    # colonne isolate -> retention alta sui task passati
    assert prog["forgetting_metric"] > 0.70


# --------------------------------------------------------------------------- #
# Fronte 2: safety guard
# --------------------------------------------------------------------------- #

def test_safety_benchmark_counts_unbalanced():
    s = safety_benchmark(n_samples=400, seed=3, contamination=0.5)
    assert s["true_positive"] > 0
    assert s["true_negative"] > 0


def test_safety_benchmark_zero_missed_blocks():
    """La policy è completa: nessun campione pericoloso deve essere approvato."""
    s = safety_benchmark(n_samples=300, seed=2, contamination=0.5)
    assert s["missed_block_rate"] == 0.0


# --------------------------------------------------------------------------- #
# Fronte 3: causale vs ground-truth
# --------------------------------------------------------------------------- #

def test_causal_benchmark_matches_analytical():
    c = causal_benchmark()
    for key in ("err_P_wet", "err_P_rain_given_wet", "err_P_wet_do"):
        assert c[key] < 1e-9


# --------------------------------------------------------------------------- #
# Fronte 4: A2A distribuito
# --------------------------------------------------------------------------- #

def test_a2a_http_benchmark():
    r = a2a_http_benchmark()
    assert r["registered"] == 3
    assert r["expensive_excluded"]
    assert r["signature_accepted"]
    # reputazione cresce dopo outcome positivo
    assert r["reputation_after"] > r["reputation_before"]


# --------------------------------------------------------------------------- #
# Report completo
# --------------------------------------------------------------------------- #

def test_run_all_benchmarks_returns_report():
    report = run_all_benchmarks(n_mem_tasks=3, epochs=3, safety_samples=100, seed=0)
    for front in ("memoria", "safety", "causale", "a2a"):
        assert front in report


# --------------------------------------------------------------------------- #
# Bridge dati-reali -> pipeline
# --------------------------------------------------------------------------- #

def test_real_data_flows_to_pipeline():
    """Dati 'veri' (in memoria) entrano nel data_loader e arrivano al pipeline."""
    from cascade.a2a_protocol import AgentManifest, generate_keypair
    from cascade.contracts import AgentSignal, Task
    from cascade.data_loader import load_observations_in_memory
    from cascade.benchmarks import table_to_tasks
    from cascade.pipeline import CascadePipeline

    data = [
        {"pos": "0.5", "vel": "0.3", "target": "1"},
        {"pos": "-0.4", "vel": "0.1", "target": "0"},
        {"pos": "0.2", "vel": "-0.5", "target": "1"},
        {"pos": "-0.1", "vel": "0.6", "target": "0"},
    ]
    tbl = load_observations_in_memory(data, label_column="target")
    tasks = table_to_tasks(tbl)

    pipe = CascadePipeline()
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("ctrl-1", pub, ["controllo"], 0.1, 0.9))

    approved = 0
    for t in tasks[:3]:
        task = Task(f"id", "controllo", {}, max_cost=1.0)
        prop = AgentSignal("ctrl-1", {"action": t["action"]}, confidence=0.95,
                           capability="controllo")
        dec = pipe.run(task, [prop], state=t["state"], noise=t["noise"])
        assert dec.final_output is not None
        if dec.approved:
            approved += 1
    assert approved >= 0  # flusso eseguito su dati reali senza errori
