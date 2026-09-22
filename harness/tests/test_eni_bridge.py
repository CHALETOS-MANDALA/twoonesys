"""Test del ponte ENI <-> Pipeline (con ENI simulato, nessuna rete)."""

import asyncio

import pytest

from cascade.contracts import AgentSignal, Task
from cascade.eni_brain import ENIBrain, fake_eni_response


def test_eni_propose_extracts_real_confidence():
    brain = ENIBrain(call_fn=fake_eni_response)
    sig = asyncio.run(brain.propose("problema di test", default_action=1.0))
    assert isinstance(sig, AgentSignal)
    # azione estratta dalla rationale ENI ("2.5")
    assert sig.proposal["action"] == 2.5
    # confidenza reale, non fittizia: 0.6*0.9 + 0.4*0.80 = 0.86
    assert 0.85 < sig.confidence < 0.87
    assert sig.agent_id == "eni-1"


def test_eni_manifest_registers():
    brain = ENIBrain(call_fn=fake_eni_response)
    man = brain.manifest()
    assert man.agent_id == "eni-1"
    assert "controllo" in man.capabilities


def test_eni_to_pipeline_end_to_end():
    """ENI (simulato) propone -> pipeline valida con causale + guard Z3."""
    import asyncio

    pytest.importorskip("torch")
    from cascade.a2a_protocol import generate_keypair
    from cascade.neurosymbolic_guard import ConfidenceLevel
    from cascade.pipeline import CascadePipeline, PipelineConfig

    brain = ENIBrain(call_fn=fake_eni_response)
    # soglia di confidenza adeguata al dominio esplorativo: 0.86 (ENI) > 0.80
    pipe = CascadePipeline(PipelineConfig(confidence_threshold=ConfidenceLevel.EXPLORATORY))
    # registra ENI come agente A2A
    man = brain.manifest()
    pipe.register_agent(man)

    sig = asyncio.run(brain.propose("controllo oscillatore", default_action=1.0))
    task = Task("t_eni", "controllo", {}, max_cost=1.0)
    dec = pipe.run(task, [sig], state=[0.5, 0.3], noise=False)
    # il flusso completa con un output (azione estratta 2.5, dentro budget 5)
    assert dec.final_output is not None
    assert dec.agent_id == "eni-1"
    # la confidenza proviene da ENI, non hardcodata
    assert sig.confidence > 0.8
