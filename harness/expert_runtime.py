"""Verified expert routing and bounded resident-memory runtime."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import torch


class ExpertRuntimeError(RuntimeError):
    """Raised for invalid artifacts, plans, or resource limits."""


@dataclass(frozen=True)
class ExpertSpec:
    expert_id: str
    path: Path
    tags: tuple[str, ...]
    sha256: str
    size_bytes: int

    @classmethod
    def from_file(cls, expert_id: str, path: str | Path,
                  tags: tuple[str, ...]) -> "ExpertSpec":
        artifact = Path(path)
        if not artifact.is_file():
            raise ExpertRuntimeError(f"expert artifact missing: {artifact}")
        payload = artifact.read_bytes()
        return cls(expert_id, artifact, tuple(sorted(set(tags))),
                   hashlib.sha256(payload).hexdigest(), len(payload))


@dataclass(frozen=True)
class RoutingDecision:
    query_digest: str
    selected: tuple[str, ...]
    scores: tuple[tuple[str, float], ...]
    evicted: tuple[str, ...]
    required_bytes: int
    backend: str


@dataclass(frozen=True)
class RuntimeResult:
    decision: RoutingDecision
    artifact_digest: str
    loaded_bytes: int
    verified: bool


class ExpertRuntime:
    """Bounded resident artifact manager with online routing calibration."""

    def __init__(self, specs: tuple[ExpertSpec, ...], budget_bytes: int,
                 *, state_path: str | Path | None = None,
                 backend: str = "cpu"):
        if not specs:
            raise ExpertRuntimeError("at least one expert is required")
        if budget_bytes <= 0:
            raise ValueError("budget_bytes must be positive")
        if backend not in {"cpu", "cuda"}:
            raise ValueError("backend must be cpu or cuda")
        if backend == "cuda" and not torch.cuda.is_available():
            raise ExpertRuntimeError("CUDA backend requested but no CUDA device is available")
        self.specs = {spec.expert_id: spec for spec in specs}
        if len(self.specs) != len(specs):
            raise ValueError("expert_id values must be unique")
        self.budget_bytes = budget_bytes
        self.backend = backend
        self.state_path = Path(state_path) if state_path is not None else None
        self._resident: OrderedDict[str, bytes | torch.Tensor] = OrderedDict()
        self._success = {key: 0 for key in self.specs}
        self._failure = {key: 0 for key in self.specs}
        self._load_state()

    @property
    def resident_ids(self) -> tuple[str, ...]:
        return tuple(self._resident)

    @property
    def resident_bytes(self) -> int:
        return sum(payload.numel() if isinstance(payload, torch.Tensor)
                   else len(payload) for payload in self._resident.values())

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if data.get("budget_bytes") != self.budget_bytes:
            raise ExpertRuntimeError("routing state budget does not match runtime")
        for expert_id in self.specs:
            self._success[expert_id] = int(data.get("success", {}).get(expert_id, 0))
            self._failure[expert_id] = int(data.get("failure", {}).get(expert_id, 0))

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "budget_bytes": self.budget_bytes,
                   "success": self._success, "failure": self._failure}
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.state_path)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", text.lower()))

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _score(self, query_tokens: set[str], spec: ExpertSpec) -> float:
        overlap = len(query_tokens.intersection(spec.tags))
        trials = self._success[spec.expert_id] + self._failure[spec.expert_id]
        posterior = (self._success[spec.expert_id] + 1) / (trials + 2)
        return float(2 * overlap + posterior + math.log1p(trials) * 0.01)

    def plan(self, query: str, *, max_experts: int = 2) -> RoutingDecision:
        if not query.strip():
            raise ValueError("query must not be empty")
        if max_experts <= 0:
            raise ValueError("max_experts must be positive")
        tokens = self._tokens(query)
        ranked = sorted(self.specs.values(),
                        key=lambda spec: (-self._score(tokens, spec), spec.expert_id))
        selected: list[str] = []
        required = 0
        for spec in ranked:
            if len(selected) == max_experts:
                break
            if spec.size_bytes <= self.budget_bytes - required:
                selected.append(spec.expert_id)
                required += spec.size_bytes
        if not selected:
            raise ExpertRuntimeError("no expert combination fits memory budget")
        keep = set(selected)
        evicted = tuple(expert_id for expert_id in self._resident if expert_id not in keep)
        scores = tuple((spec.expert_id, self._score(tokens, spec)) for spec in ranked)
        return RoutingDecision(self._digest(query), tuple(selected), scores,
                               evicted, required, self.backend)

    def execute(self, query: str, *, max_experts: int = 2) -> RuntimeResult:
        decision = self.plan(query, max_experts=max_experts)
        for expert_id in decision.evicted:
            self._resident.pop(expert_id, None)
        for expert_id in decision.selected:
            if expert_id in self._resident:
                self._resident.move_to_end(expert_id)
                continue
            spec = self.specs[expert_id]
            payload = spec.path.read_bytes()
            if len(payload) != spec.size_bytes or hashlib.sha256(payload).hexdigest() != spec.sha256:
                raise ExpertRuntimeError(f"expert artifact changed: {expert_id}")
            if self.resident_bytes + len(payload) > self.budget_bytes:
                raise ExpertRuntimeError("resident memory budget exceeded")
            self._resident[expert_id] = (
                torch.frombuffer(bytearray(payload), dtype=torch.uint8).clone().cuda()
                if self.backend == "cuda" else payload)
        combined = b"".join(self._payload_bytes(self._resident[expert_id])
                            for expert_id in decision.selected)
        return RuntimeResult(decision, hashlib.sha256(combined).hexdigest(),
                             sum(len(self._resident[key]) for key in decision.selected), True)

    def feedback(self, selected: tuple[str, ...], success: bool) -> None:
        target = self._success if success else self._failure
        for expert_id in selected:
            if expert_id not in self.specs:
                raise ExpertRuntimeError(f"unknown expert: {expert_id}")
            target[expert_id] += 1
        self._save_state()

    def verify_resident(self) -> bool:
        if self.resident_bytes > self.budget_bytes:
            return False
        return all(
            self._payload_size(payload) == self.specs[expert_id].size_bytes
            and hashlib.sha256(self._payload_bytes(payload)).hexdigest() == self.specs[expert_id].sha256
            for expert_id, payload in self._resident.items())

    @staticmethod
    def _payload_size(payload: bytes | torch.Tensor) -> int:
        return payload.numel() if isinstance(payload, torch.Tensor) else len(payload)

    @staticmethod
    def _payload_bytes(payload: bytes | torch.Tensor) -> bytes:
        if isinstance(payload, torch.Tensor):
            return bytes(payload.detach().cpu().tolist())
        return payload