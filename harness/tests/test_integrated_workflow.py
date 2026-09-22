import os
from pathlib import Path

import pytest

from cascade.integrated_workflow import IntegratedWorkflow
from cascade.ollama_router import ModelProfile, OllamaClient, OllamaRouter
from cascade.outcome_log import OutcomeLog
from cascade.workers import run_verified


PRISM_PATH = os.environ.get("CASCADE_PRISM_PATH")


@pytest.mark.skipif(not PRISM_PATH, reason="CASCADE_PRISM_PATH is not configured")
def test_real_prism_kiarnel_chain_is_verified():
    report = run_verified(
        "mathematical verification",
        ["A mathematical claim needs deterministic evidence.",
         "This unrelated text discusses music."],
        calc_kind="zeron", calc_args={"n": 1})

    # senza claim del modello la catena non si auto-verifica
    assert report.verdict.ok is False
    assert report.verdict.code.value == "model_value_missing"


def test_workflow_blocks_without_verified_model_output(tmp_path):
    client = OllamaClient(base_url="http://127.0.0.1:1", timeout=0.1)
    router = OllamaRouter(
        (ModelProfile("unreachable-model", ("verification",)),), client=client)
    workflow = IntegratedWorkflow(router, log=OutcomeLog(tmp_path / "events.jsonl"),
                                  action_root=tmp_path / "actions")

    result = workflow.run("blocked-001", "verification request", [
        "Deterministic evidence is required."]) 

    assert result.generation.status == "failed"
    assert result.action_status == "blocked"
    assert not list((tmp_path / "actions").glob("*.json"))


@pytest.mark.skipif(not PRISM_PATH, reason="CASCADE_PRISM_PATH is not configured")
@pytest.mark.integration
def test_live_ollama_workflow_writes_and_logs_real_action(tmp_path):
    available = OllamaClient().models()
    model = "deepseek-r1:7b"
    if model not in available:
        pytest.skip(f"{model} is not installed in Ollama")
    router = OllamaRouter((ModelProfile(model, ("verification", "math")),),
                          client=OllamaClient(timeout=180))
    log = OutcomeLog(tmp_path / "events.jsonl")
    workflow = IntegratedWorkflow(router, log=log, action_root=tmp_path / "actions")

    result = workflow.run("live-001", "Explain verified mathematical evidence briefly.", [
        "A mathematical claim needs deterministic evidence.",
        "This unrelated text discusses music."], n=1)

    assert result.generation.status == "succeeded"
    # prosa del modello != claim tipizzato: il gate deve bloccare
    assert result.evidence.verdict.ok is False
    assert result.action_status == "blocked"
    assert not (tmp_path / "actions" / "live-001.json").is_file()
    assert log.load().size == 1