"""Integration test end-to-end del pipeline CASCADE (tutti i layer)."""

import torch
import pytest

from cascade.a2a_protocol import AgentManifest, generate_keypair
from cascade.contracts import AgentSignal, Task
from cascade.pipeline import CascadePipeline, PipelineConfig, PipelineConfig


def make_pipe() -> CascadePipeline:
    pipe = CascadePipeline()
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("ctrl-1", pub, ["controllo"], 0.1, 0.9))
    return pipe


def ctrl_proposal(action: float, confidence: float = 0.96) -> AgentSignal:
    return AgentSignal("ctrl-1", {"action": action}, confidence=confidence,
                       capability="controllo")


def test_approved_certified_flow():
    pipe = make_pipe()
    task = Task("t1", "controllo", {"pos": 0.5, "vel": 0.3}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(1.2)], state=[0.5, 0.3], noise=False)
    assert dec.approved
    assert dec.certified
    assert dec.final_output == {"action": 1.2, "note": "autorizzato e certificato"}
    assert dec.agent_id == "ctrl-1"
    assert dec.forecast is not None
    assert dec.evidence is not None


def test_no_agent_flow():
    pipe = CascadePipeline()  # nessun agente registrato
    task = Task("t1", "controllo", {"pos": 0.5}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(1.2)], state=[0.5, 0.3], noise=False)
    assert not dec.approved
    assert not dec.certified
    assert any(v["layer"] == "a2a" for v in dec.violations)


def test_low_confidence_rejected():
    pipe = make_pipe()
    task = Task("t1", "controllo", {"pos": 0.5}, max_cost=1.0)
    # presenta confidenza bassa -> guard la respinge
    dec = pipe.run(task, [ctrl_proposal(1.2, confidence=0.2)],
                   state=[0.5, 0.3], noise=False)
    assert not dec.approved


def test_unstable_forecast_mitigates():
    pipe = make_pipe()
    task = Task("t2", "controllo", {"pos": 0.5}, max_cost=1.0)
    # azione molto alta nello stato (pos ampiamente fuori) -> vel prevista fuori soglia
    dec = pipe.run(task, [ctrl_proposal(6.0, confidence=0.98)],
                   state=[3.0, 2.0], noise=False)
    if dec.approved:
        # se approvata comunque, deve essere certificata
        assert dec.certified
    else:
        assert any(v["layer"] in ("world", "guard") for v in dec.violations)


def test_causal_counterfactual_present():
    pipe = make_pipe()
    task = Task("t3", "controllo", {"pos": 0.5}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(0.5)], state=[0.5, 0.3], noise=True)
    assert dec.evidence is not None
    assert len(dec.evidence.counterfactuals) >= 1
    # il controfattuale e' una distribuzione normalizzata
    cf = dec.evidence.counterfactuals[0]["se_non_ipercontrollo"]
    assert abs(sum(cf.values()) - 1.0) < 1e-6


def test_memory_trains_across_tasks():
    pipe = make_pipe()
    # addestra il world model su due "task" fisici e verifica che non crashi
    states = [[0.1, 0.0], [0.2, 0.05], [0.3, 0.1], [0.4, 0.15]]
    actions = [0.1, 0.2, 0.1, 0.2]
    pipe.remember(0, states, actions)
    pipe.remember(1, states, actions)
    assert len(pipe.memory.history) == 2


def test_full_sequence_memory_then_decision():
    pipe = make_pipe()
    states = [[0.1, 0.0], [0.2, 0.05], [0.3, 0.1], [0.4, 0.15]]
    actions = [0.1, 0.2, 0.1, 0.2]
    pipe.remember(0, states, actions)
    task = Task("t4", "controllo", {"pos": 0.5}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(0.8)], state=[0.4, 0.15], noise=False)
    # il pipeline continua a funzionare dopo l'addestramento continuo
    assert dec.final_output is not None


# --------------------------------------------------------------------------- #
# FIX 1 - il ragionamento causale ora DECIDE (gate sul rischio)
# --------------------------------------------------------------------------- #

def test_causal_gate_blocks_high_risk():
    """Con rumore attivo e ipercontrollo, P(incidente)>soglia deve bloccare
    (o ridurre fino ad esaurire le mitigazioni) la decisione."""
    pipe = make_pipe()
    task = Task("t5", "controllo", {"pos": 0.5}, max_cost=1.0)
    # azione dentro il budget ma > 70% del max -> ipercontrollo=True;
    # con noise=True l'evidenza causale diventa ad alto rischio.
    dec = pipe.run(task, [ctrl_proposal(4.0, confidence=0.98)],
                   state=[0.5, 0.3], noise=True)
    # deve aver mitigato: mai autorizzare l'azione originale da 4.0
    assert dec.final_output["action"] < 4.0
    if not dec.approved:
        # se bloccato, deve esserci una violazione causale
        causal = [v for v in dec.violations if v["layer"] == "causal"]
        assert any(v["type"] == "risk_threshold_exceeded" for v in causal)


def test_causal_gate_approves_low_risk():
    """Senza rumore e senza ipercontrollo, P(incidente) bassa -> approvazione."""
    pipe = make_pipe()
    task = Task("t6", "controllo", {"pos": 0.5}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(0.5)], state=[0.5, 0.3], noise=False)
    assert dec.approved
    assert dec.certified
    assert dec.final_output["action"] == 0.5


# --------------------------------------------------------------------------- #
# FIX 2 - policy di sicurezza unica (nessun doppio gate manuale)
# --------------------------------------------------------------------------- #

def test_no_duplicate_safety_gate():
    """La policy di sicurezza vive SOLO nel guard Z3, non c'e' un secondo check
    manuale su forecast.stable nel flusso decisionale."""
    import inspect
    from cascade import pipeline
    src = inspect.getsource(pipeline.CascadePipeline.run)
    # il vecchio doppio gate manuale (href su forecast.stable) non deve esistere
    assert "if not forecast.stable" not in src


def test_out_of_budget_action_is_mitigated():
    """Azione oltre il budget (6 > max 5): la policy unica la mitiga, mai
    autorizzata al valore pieno."""
    pipe = make_pipe()
    task = Task("t7", "controllo", {"pos": 0.5}, max_cost=1.0)
    dec = pipe.run(task, [ctrl_proposal(6.0, confidence=0.98)],
                   state=[0.5, 0.3], noise=False)
    assert dec.final_output["action"] < 6.0


# --------------------------------------------------------------------------- #
# FIX 3 - negoziazione A2A reale (reputazione), non max(confidence)
# --------------------------------------------------------------------------- #

def test_negotiation_uses_reputation_not_confidence():
    """Tra due agenti capaci, vince quello con miglior rapporto
    reputazione/costo (via negotiate()), anche se ha confidenza minore."""
    pipe = CascadePipeline()
    # agente A: confidenza massima ma alta confidenza e bassa reputazione
    # agente B: scelto per reputazione/costo
    _, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    # alice: economica, alta reputazione -> dovrebbe vincere
    pipe.register_agent(AgentManifest("alice", pub_a, ["controllo"], 0.05, 0.95))
    # bob: costosa, reputazione media -> perde
    pipe.register_agent(AgentManifest("bob", pub_b, ["controllo"], 9.0, 0.5))

    task = Task("t8", "controllo", {"pos": 0.5}, max_cost=2.0)
    proposals = [
        AgentSignal("alice", {"action": 0.4}, confidence=0.6, capability="controllo"),
        AgentSignal("bob", {"action": 0.4}, confidence=0.99, capability="controllo"),
    ]
    dec = pipe.run(task, proposals, state=[0.5, 0.3], noise=False)
    # benchè bob abbia confidenza maggiore, la negoziazione reale premia alice
    assert dec.agent_id == "alice"


# --------------------------------------------------------------------------- #
# REVIEW: DecisionCertificate firmato e verificabile
# --------------------------------------------------------------------------- #

def test_decision_carries_verifiable_certificate():
    pipe = CascadePipeline(PipelineConfig(confidence_threshold=0.5))
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("a", pub, ["controllo"], 0.1, 0.9))
    dec = pipe.run(Task("c1", "controllo", {}, max_cost=1.0),
                   [AgentSignal("a", {"action": 0.5}, confidence=0.7,
                                capability="controllo")],
                   state=[0.5, 0.3])
    assert dec.approved
    assert dec.certificate is not None
    # firma valida con la chiave pubblica del pipeline
    assert dec.certificate.verify_signature(pipe._sign_pub)
    # riproducibilita': versioni dei modelli registrate
    assert "world_model" in dec.certificate.model_versions
    assert dec.certificate.policy_version == "policy-v1"


def test_certificate_detects_corruption():
    pipe = CascadePipeline(PipelineConfig(confidence_threshold=0.5))
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("a", pub, ["controllo"], 0.1, 0.9))
    dec = pipe.run(Task("c2", "controllo", {}, max_cost=1.0),
                   [AgentSignal("a", {"action": 0.5}, confidence=0.7,
                                capability="controllo")],
                   state=[0.5, 0.3])
    cert = dec.certificate
    assert cert.verify_signature(pipe._sign_pub)
    # manomettiamo la versione della policy: la firma non deve piu' valere
    cert.policy_version = "policy-EVIL"
    assert not cert.verify_signature(pipe._sign_pub)


def test_ood_abstention():
    pipe = CascadePipeline(PipelineConfig(confidence_threshold=0.5))
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("a", pub, ["controllo"], 0.1, 0.9))
    # stato anomalo (|pos| alto) -> il world model lo rileva come OOD
    dec = pipe.run(Task("c3", "controllo", {}, max_cost=1.0),
                   [AgentSignal("a", {"action": 0.5}, confidence=0.9,
                                capability="controllo")],
                   state=[9.0, 8.0])
    assert dec.abstained
    assert "out_of_distribution" in dec.abstain_reason
    assert not dec.approved
    # anche l'astensione e' certificata
    assert dec.certificate is not None
