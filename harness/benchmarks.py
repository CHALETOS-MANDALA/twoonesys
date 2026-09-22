"""CASCADE - Benchmark veri (dominio-agnostico).

Misura NUMERI reali su tutti i layer, non "il test passa". Fronti:

1. MEMORIA   : catastrophic forgetting reale su N task, EWC on vs off.
2. SAFETY    : tasso di falso-blocco vs mancato-blocco su disturbo sistematico.
3. CAUSALE   : verifica di do-calculus e controfattuali contro ground-truth
               calcolato analiticamente.
4. A2A       : negoziazione reale via HTTP (FastAPI TestClient) con firme
               Ed25519 verificate.

Ogni funzione ritorna un dict di metriche, cosi' i risultati sono confrontabili
tra run e possono essere asseriti in test.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import torch
import torch.nn as nn

try:
    from .a2a_protocol import (
        AgentManifest,
        create_app,
        generate_keypair,
        sign_payload,
    )
    from .causal_engine import CPD, CausalModel, CausalNode
    from .continuous_memory import ContinualLearner, ProgressiveNet
except ImportError:  # esecuzione diretta come script
    from a2a_protocol import AgentManifest, create_app, generate_keypair, sign_payload
    from causal_engine import CPD, CausalModel, CausalNode
    from continuous_memory import ContinualLearner, ProgressiveNet


# --------------------------------------------------------------------------- #
# Fronte 1: memoria continua / catastrophic forgetting
# --------------------------------------------------------------------------- #


def permuted_tasks(n_tasks: int, dim: int = 16, per_task: int = 800,
                   seed: int = 0) -> list[torch.utils.data.DataLoader]:
    """Crea N task CONFLITTUALI (stile permuted/continuous learning).

    Ogni task separa UNA feature diversa con una soglia diversa, cosi' la rete
    condivisa DEVE dimenticare i separator precedenti per imparare i nuovi.
    Questo e' il setup standard che produce vero catastrophic forgetting e
    rende visibile il valore di EWC.
    """
    rng = np.random.default_rng(seed)
    loaders = []
    for t in range(n_tasks):
        x = rng.normal(size=(per_task, dim)).astype(np.float32)
        feat = t % dim
        y = (x[:, feat] > (t % 3 - 1) * 0.5).astype(np.int64)
        xs = torch.tensor(x)
        ys = torch.tensor(y)
        loaders.append(torch.utils.data.DataLoader(
            list(zip(xs, ys)), batch_size=32, shuffle=True
        ))
    return loaders


def _shared_net(dim: int = 12) -> nn.Module:
    """Rete a parametri CONDIVISI (un solo set di pesi per tutti i task).
    Qui EWC e' l'unica difesa contro il forgetting: perfetto per misurarlo."""
    return nn.Sequential(
        nn.Linear(dim, 64),
        nn.ReLU(),
        nn.Linear(64, 2),
    )


def evaluate_forgetting(tasks: list[torch.utils.data.DataLoader],
                        use_ewc: bool, epochs_per_task: int = 4,
                        seed: int = 0,
                        progressive: bool = False) -> dict[str, Any]:
    """Addestra su N task in sequenza e valuta l'accuratezza su TUTTI i task
    alla fine.

    - progressive=True : ProgressiveNet (colonne isolate) -> no forgetting
      strutturale; EWC e' ridondante qui.
    - progressive=False: rete condivisa -> EWC E' l'unica difesa reale; questo
      misura il valore vero di EWC.
    """
    torch.manual_seed(seed)
    dim = tasks[0].dataset[0][0].shape[0]
    if progressive:
        model = ProgressiveNet(input_dim=dim, hidden_dim=32, output_dim=2)
        model.add_task()
    else:
        model = _shared_net(dim)
    loss_fn = nn.CrossEntropyLoss()
    lr = ContinualLearner(
        model, lr=1e-2, lambda_ewc=3000.0 if use_ewc else 0.0,
        epochs_per_task=epochs_per_task,
    )

    n = len(tasks)
    for t in range(n):
        if progressive and t > 0:
            model.freeze_previous()
            model.add_task()
        lr.train_task(t, tasks[t], loss_fn, task_lr=1e-2)

    # valuta l'accuratezza per OGNI task (anche i passati)
    accs = {}
    model.eval()
    with torch.no_grad():
        for t, dl in enumerate(tasks):
            correct = 0
            total = 0
            for x, y in dl:
                out = model(x, task_id=t) if progressive else model(x)
                pred = out.argmax(dim=1)
                correct += (pred == y).sum().item()
                total += y.size(0)
            accs[f"task_{t}"] = correct / max(total, 1)

    # forgetting = accuratezza media sui primi (n-1) task a fine training
    first_accs = [accs[f"task_{t}"] for t in range(n - 1)]
    final_accs = [accs[f"task_{t}"] for t in range(n)]
    forgetting = sum(first_accs) / len(first_accs) if first_accs else 0.0
    return {
        "use_ewc": use_ewc,
        "progressive": progressive,
        "final_avg_accuracy": float(np.mean(final_accs)),
        "forgetting_metric": float(forgetting),
        "accuracies": accs,
    }


# --------------------------------------------------------------------------- #
# Fronte 2: safety guard (falso-blocco vs mancato-blocco)
# --------------------------------------------------------------------------- #

try:
    from .neurosymbolic_guard import ConfidenceLevel, NeurosymbolicGuard, SymbolicContract
except ImportError:
    from neurosymbolic_guard import ConfidenceLevel, NeurosymbolicGuard, SymbolicContract
def build_safety_bench() -> tuple[NeurosymbolicGuard, list[SymbolicContract]]:
    """Guard con una policy di sicurezza su due variabili (velocita', dose)."""
    import z3

    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    vel = z3.Real("velocita")
    guard.add_contract(SymbolicContract(
        name="vel_max",
        expressions=[z3.And(vel >= -3.0, vel <= 3.0)],
        symbols={"velocita": vel},
    ))
    dose = z3.Real("dose")
    guard.add_contract(SymbolicContract(
        name="dose_max",
        expressions=[z3.And(dose >= 0.0, dose <= 100.0)],
        symbols={"dose": dose},
    ))
    return guard, []


def safety_benchmark(n_samples: int = 200, seed: int = 0,
                     contamination: float = 0.25) -> dict[str, float]:
    """Genera campioni con una parte pericolosa (viola la policy) e valuta il
    guard. Metriche: falso-blocco (campioni sani bloccati) e mancato-blocco
    (campioni pericolosi approvati)."""
    rng = np.random.default_rng(seed)
    guard, _ = build_safety_bench()
    true_positive = false_positive = true_negative = false_negative = 0
    for i in range(n_samples):
        dangerous = rng.random() < contamination
        if dangerous:
            # viola ALMENO un vincolo
            vel = rng.uniform(3.5, 8.0) if rng.random() < 0.5 else rng.uniform(-8.0, -3.5)
            dose = rng.uniform(0.0, 100.0)
        else:
            vel = rng.uniform(-3.0, 3.0)
            dose = rng.uniform(0.0, 100.0)
        out, ok = guard.validate(
            {"velocita": vel, "dose": dose},
            {"velocita": vel, "dose": dose, "confidence": 0.95},
        )
        if dangerous and not ok:
            true_positive += 1      # giustamente bloccato
        elif dangerous and ok:
            false_negative += 1     # PERICOLOSO approvato (mancato-blocco)
        elif not dangerous and ok:
            true_negative += 1      # giustamente approvato
        else:
            false_positive += 1     # sano bloccato (falso-blocco)

    return {
        "missed_block_rate": false_negative / max(true_positive + false_negative, 1),
        "false_block_rate": false_positive / max(false_positive + true_negative, 1),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "false_positive": false_positive,
    }


# --------------------------------------------------------------------------- #
# Fronte 3: causale contro ground-truth analitico
# --------------------------------------------------------------------------- #


def _analytical_sprinkler() -> dict[str, Any]:
    """Ground-truth del classico sprinkler (da libro di riferimento).
    P(bagnato=T)=0.71, P(pioggia=T|bagnato=T)=0.6831, P(bagnato|do(sprinkler=F))."""
    # P(pioggia)=0.5, P(sprinkler)=0.5, P(bagnato|p,s)
    p_wet_true = 0.5 * 0.5 * 0.99 + 0.5 * 0.5 * 0.95 + 0.5 * 0.5 * 0.90 + 0.5 * 0.5 * 0.0
    # P(pioggia=T|wet) = P(wet|rainT)*P(rain)/P(wet)
    p_wet_rain = 0.5 * (0.99 + 0.95)
    p_rain_wet = (p_wet_rain * 0.5) / p_wet_true
    # do(sprinkler=F): P(wet)=P(wet|rain)*P(rain)=0.5*0.95 + ... con sprinkler=F
    # -> solo ramo rain: P(wet)=P(rain=T)*0.95 + P(rain=F)*0.0 = 0.5*0.95=0.475
    return {
        "P(wet)": p_wet_true,
        "P(rain|wet)": p_rain_wet,
        "P(wet|do(sprinkler=F))": 0.475,
    }


def causal_benchmark() -> dict[str, float]:
    """Confronta il motore causale contro il ground-truth analitico."""
    try:
        from .causal_engine import sprinkler_model
    except ImportError:
        from causal_engine import sprinkler_model
    m = sprinkler_model()
    gt = _analytical_sprinkler()

    p_wet = m.posterior("bagnato")[True]
    p_rain_wet = m.posterior("pioggia", {"bagnato": True})[True]
    p_wet_do = m.do("bagnato", {"sprinkler": False})[True]

    return {
        "err_P_wet": abs(p_wet - gt["P(wet)"]),
        "err_P_rain_given_wet": abs(p_rain_wet - gt["P(rain|wet)"]),
        "err_P_wet_do": abs(p_wet_do - gt["P(wet|do(sprinkler=F))"]),
        "gt_P_wet": gt["P(wet)"],
        "gt_P_rain_given_wet": gt["P(rain|wet)"],
        "gt_P_wet_do": gt["P(wet|do(sprinkler=F))"],
        "obs_P_wet": p_wet,
        "obs_P_rain_given_wet": p_rain_wet,
        "obs_P_wet_do": p_wet_do,
    }


# --------------------------------------------------------------------------- #
# Fronte 4: A2A distribuito via HTTP (firme verificate)
# --------------------------------------------------------------------------- #


def a2a_http_benchmark() -> dict[str, Any]:
    """Registra agenti, negozia (via endpoint), e verifica firme Ed25519 su
    report. Usa FastAPI TestClient (stack HTTP reale, in-process)."""
    from fastapi.testclient import TestClient

    client = TestClient(create_app())

    # registra 3 agenti
    agents = []
    for name, cost, rep in [("a1", 0.5, 0.9), ("a2", 0.2, 0.95), ("a3", 10.0, 0.99)]:
        priv, pub = generate_keypair()
        r = client.post("/register", json={
            "agent_id": name,
            "public_key_hex": pub.hex(),
            "capabilities": ["vision", "nlp"],
            "cost_per_call": cost,
            "base_reputation": rep,
        })
        agents.append({"name": name, "priv": priv, "pub": pub})
        assert r.status_code == 200, r.text

    # discovery
    disc = client.get("/discover", params={"capability": "vision", "max_cost": 5.0})
    assert disc.status_code == 200
    found = [a["agent_id"] for a in disc.json()["agents"]]
    assert "a1" in found and "a2" in found and "a3" not in found  # a3 costoso

    # report con envelope firmato + nonce + timestamp -> accepted
    from .a2a_protocol import SignedEnvelope

    winner = agents[0]
    env = SignedEnvelope.wrap(winner["priv"], winner["name"],
                              {"task_id": "t1", "result": {"ok": True}, "outcome": 0.95})
    r = client.post("/report", json={
        "agent_id": env.agent_id,
        "nonce": env.nonce,
        "timestamp": env.timestamp,
        "payload": env.payload,
        "signature_hex": env.signature,
    })
    assert r.status_code == 200, r.text
    rep_after = r.json()["new_reputation"]

    # replay dello STESSO envelope -> deve essere rifiutato (409)
    r2 = client.post("/report", json={
        "agent_id": env.agent_id,
        "nonce": env.nonce,
        "timestamp": env.timestamp,
        "payload": env.payload,
        "signature_hex": env.signature,
    })
    assert r2.status_code == 409, f"replay non rilevato: {r2.status_code} {r2.text}"

    return {
        "registered": 3,
        "discovered_capable": len(found),
        "expensive_excluded": "a3" not in found,
        "signature_accepted": True,
        "replay_detected": True,
        "reputation_before": 0.9,
        "reputation_after": rep_after,
    }


# --------------------------------------------------------------------------- #
# Bridge dati-reali <-> pipeline
# --------------------------------------------------------------------------- #


def table_to_tasks(tbl, capability: str = "controllo") -> list[dict]:
    """Converte un dataset reale (LoadedTable) in richieste per il pipeline.

    Ogni riga numerica diventa uno stato su cui far decidere un agente:
    action = valore della feature piu' variabile (proxy di un comando),
    state  = la riga come stato [pos, vel] se 2+ feature.
    Ritorna una lista di dict {state, action, noise}.
    """
    X = tbl.numeric_matrix
    if X is None:
        tbl.to_numeric(tbl.label_column)
        X = tbl.numeric_matrix
    tasks = []
    for i in range(len(X)):
        row = X[i]
        # action proxy: la feature con piu' dispersione (varianza massima)
        action = float(row[np.argmax(np.var(X, axis=0))]) if len(row) else 0.0
        state = [float(row[0]), float(row[1])] if len(row) >= 2 else [float(row[0]) if len(row) else 0.0, 0.0]
        tasks.append({"state": state, "action": min(max(action, -5.0), 5.0),
                      "noise": False})
    return tasks


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def run_all_benchmarks(n_mem_tasks: int = 5, epochs: int = 5,
                       safety_samples: int = 150, seed: int = 0) -> dict[str, Any]:
    """Esegue tutti i benchmark e ritorna un report completo."""
    report: dict[str, Any] = {}

    # Fronte 1: memoria
    tasks = permuted_tasks(n_mem_tasks, dim=16, seed=seed)
    # rete CONDIVISA (EWC = unica difesa) - misura il valore vero di EWC
    ewc_off = evaluate_forgetting(tasks, use_ewc=False, epochs_per_task=epochs, seed=seed)
    ewc_on = evaluate_forgetting(tasks, use_ewc=True, epochs_per_task=epochs, seed=seed)
    # rete PROGRESSIVA (colonne isolate) - no forgetting strutturale
    prog = evaluate_forgetting(tasks, use_ewc=False, epochs_per_task=epochs,
                               seed=seed, progressive=True)
    report["memoria"] = {
        "shared_net_ewc_off": ewc_off["forgetting_metric"],
        "shared_net_ewc_on": ewc_on["forgetting_metric"],
        "ewc_improves_shared": ewc_on["forgetting_metric"] > ewc_off["forgetting_metric"] + 0.01,
        "progressive_forgetting": prog["forgetting_metric"],
        "progressive_has_minimal_forgetting": prog["forgetting_metric"] > 0.9,
    }

    # Fronte 2: safety
    report["safety"] = safety_benchmark(n_samples=safety_samples, seed=seed)

    # Fronte 3: causale
    report["causale"] = causal_benchmark()

    # Fronte 4: A2A
    report["a2a"] = a2a_http_benchmark()

    return report


def print_report(report: dict[str, Any]) -> None:
    print("=" * 52)
    print("CASCADE - REPORT BENCHMARK VERI")
    print("=" * 52)
    mem = report["memoria"]
    print(f"[MEMORIA] rete CONDIVISA  forgetting senza EWC: {mem['shared_net_ewc_off']:.3f}")
    print(f"[MEMORIA] rete CONDIVISA  forgetting con EWC:   {mem['shared_net_ewc_on']:.3f}  "
          f"({'EWC aiuta' if mem['ewc_improves_shared'] else 'EWC non aiuta'})")
    print(f"[MEMORIA] rete PROGRESSIVA retention passati: {mem['progressive_forgetting']:.3f}  "
          f"({'buona (isolamento colonne)' if mem['progressive_has_minimal_forgetting'] else 'moderata'})")
    saf = report["safety"]
    print(f"[SAFETY] mancato-blocco: {saf['missed_block_rate']:.3f}")
    print(f"[SAFETY] falso-blocco:   {saf['false_block_rate']:.3f}")
    cas = report["causale"]
    print(f"[CAUSALE] |err| P(wet):           {cas['err_P_wet']:.2e}")
    print(f"[CAUSALE] |err| P(rain|wet):      {cas['err_P_rain_given_wet']:.2e}")
    print(f"[CAUSALE] |err| P(wet|do):        {cas['err_P_wet_do']:.2e}")
    a2a = report["a2a"]
    print(f"[A2A] agenti registrati: {a2a['registered']}, scoperti: {a2a['discovered_capable']}, "
          f"costo elevato escluso: {a2a['expensive_excluded']}")
    print(f"[A2A] firma accettata: {a2a['signature_accepted']}, "
          f"reputazione {a2a['reputation_before']} -> {a2a['reputation_after']:.3f}")


if __name__ == "__main__":
    import sys
    print_report(run_all_benchmarks())
