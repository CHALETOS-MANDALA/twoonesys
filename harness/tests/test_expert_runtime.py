from pathlib import Path

import pytest
import torch

from cascade.expert_runtime import ExpertRuntime, ExpertRuntimeError, ExpertSpec


def _runtime(tmp_path: Path, budget: int = 16,
             backend: str = "cpu") -> ExpertRuntime:
    artifacts = tmp_path / "experts"
    artifacts.mkdir()
    contents = {
        "finance": b"finance-expert-payload",
        "code": b"code-expert-payload",
        "general": b"general-expert-payload",
    }
    specs = []
    for expert_id, tags in (
        ("finance", ("finance", "risk")),
        ("code", ("code", "python")),
        ("general", ("general", "default")),
    ):
        path = artifacts / f"{expert_id}.bin"
        path.write_bytes(contents[expert_id])
        specs.append(ExpertSpec.from_file(expert_id, path, tags))
    return ExpertRuntime(specs, budget, state_path=tmp_path / "router.json",
                         backend=backend)


def test_real_artifacts_are_selected_loaded_and_verified(tmp_path):
    runtime = _runtime(tmp_path, budget=64)

    result = runtime.execute("finance risk analysis", max_experts=1)

    assert result.decision.selected == ("finance",)
    assert result.verified is True
    assert runtime.resident_ids == ("finance",)
    assert runtime.verify_resident() is True
    assert result.loaded_bytes == len(b"finance-expert-payload")


def test_budget_evicts_inactive_experts_and_never_overcommits(tmp_path):
    runtime = _runtime(tmp_path, budget=45)
    first = runtime.execute("finance", max_experts=1)
    second = runtime.execute("code", max_experts=1)

    assert first.decision.selected == ("finance",)
    assert second.decision.selected == ("code",)
    assert second.decision.evicted == ("finance",)
    assert runtime.resident_ids == ("code",)
    assert runtime.resident_bytes <= 45


def test_feedback_changes_routing_and_survives_restart(tmp_path):
    runtime = _runtime(tmp_path, budget=64)
    for _ in range(8):
        runtime.feedback(("general",), success=True)
    runtime.feedback(("finance",), success=False)

    before = runtime.plan("unclassified request", max_experts=1)
    restarted = ExpertRuntime(tuple(runtime.specs.values()), 64,
                              state_path=tmp_path / "router.json")
    after = restarted.plan("unclassified request", max_experts=1)

    assert before.selected == ("general",)
    assert after.selected == before.selected
    assert (tmp_path / "router.json").is_file()


def test_artifact_tampering_is_rejected(tmp_path):
    runtime = _runtime(tmp_path, budget=64)
    runtime.specs["finance"].path.write_bytes(b"tampered")

    with pytest.raises(ExpertRuntimeError, match="artifact changed"):
        runtime.execute("finance", max_experts=1)


def test_no_artifact_fits_budget(tmp_path):
    runtime = _runtime(tmp_path, budget=1)

    with pytest.raises(ExpertRuntimeError, match="fits memory budget"):
        runtime.plan("finance", max_experts=1)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA device unavailable")
def test_cuda_backend_loads_real_tensor_and_verifies_hash(tmp_path):
    runtime = _runtime(tmp_path, budget=64, backend="cuda")

    result = runtime.execute("code python", max_experts=1)

    assert result.decision.backend == "cuda"
    assert result.verified is True
    assert runtime.verify_resident() is True
    assert runtime._resident["code"].is_cuda