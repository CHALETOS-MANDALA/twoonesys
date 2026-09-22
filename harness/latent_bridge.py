"""Adapter between Latent Brain+/SIFT and CASCADE contracts."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LatentBridgeError(RuntimeError):
    """Raised when the real Latent Brain+/SIFT runtime cannot be loaded."""


@dataclass(frozen=True)
class LatentProposal:
    """Typed proposal emitted by Latent Brain+ before CASCADE verification."""

    text: str
    confidence: float
    confidence_kind: str
    coherence: float
    memory: dict[str, Any]
    relevances: dict[str, float]
    contributions: tuple[dict[str, Any], ...]
    latency_seconds: float

    def to_agent_signal(self, *, agent_id: str = "latent-brain-plus"):
        from .contracts import AgentSignal

        return AgentSignal(
            agent_id=agent_id,
            proposal={
                "text": self.text,
                "coherence": self.coherence,
                "confidence_kind": self.confidence_kind,
                "memory": self.memory,
                "relevances": self.relevances,
                "contributions": list(self.contributions),
            },
            confidence=self.confidence,
            capability="reasoning",
        )


class LatentBrainBridge:
    """Loads the real SIFTFramework and forwards runs and feedback."""

    def __init__(self, framework: Any):
        self.framework = framework

    @classmethod
    def from_sift(cls, *, sift_path: str | Path | None = None,
                  backend: str = "ollama", model: str = "deepseek-r1:7b",
                  memory_dir: str | Path | None = None) -> "LatentBrainBridge":
        root = Path(sift_path or os.environ.get("CASCADE_SIFT_PATH", ""))
        if not root:
            root = Path(__file__).resolve().parent.parent / "sift-framework"
        source = root / "src"
        if not source.is_dir():
            raise LatentBridgeError(f"SIFT source directory missing: {source}")
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        try:
            from sift import SIFTConfig, SIFTFramework
        except Exception as exc:  # noqa: BLE001
            raise LatentBridgeError(f"cannot import SIFTFramework: {exc}") from exc
        config = SIFTConfig(backend=backend, ollama_model=model,
                            memory_dir=str(memory_dir) if memory_dir else None)
        try:
            return cls(SIFTFramework.auto(config))
        except Exception as exc:  # noqa: BLE001
            raise LatentBridgeError(f"cannot initialize Latent Brain+: {exc}") from exc

    def propose(self, prompt: str, *, user_feedback: float | None = None) -> LatentProposal:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        try:
            result = self.framework.run(prompt, user_feedback=user_feedback)
        except Exception as exc:  # noqa: BLE001
            raise LatentBridgeError(f"Latent Brain+ run failed: {exc}") from exc
        metadata = dict(result.metadata or {})
        memory = dict(metadata.get("memory") or {})
        coherence = max(0.0, min(1.0, float(result.coherence)))
        return LatentProposal(
            text=str(result.text).strip(),
            confidence=coherence,
            confidence_kind="coherence_uncalibrated",
            coherence=coherence,
            memory=memory,
            relevances={str(k): float(v) for k, v in result.relevances.items()},
            contributions=tuple(dict(item) for item in result.contributions),
            latency_seconds=float(result.latency_parallel),
        )