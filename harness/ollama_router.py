"""Ollama model router with verified fallback and persistent outcomes."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


class OllamaError(RuntimeError):
    """Raised when Ollama cannot provide a valid generation."""


@dataclass(frozen=True)
class ModelProfile:
    name: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class GenerationResult:
    model: str
    text: str
    status: str
    latency_ms: float
    attempts: tuple[str, ...]
    error: str | None = None


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def models(self) -> tuple[str, ...]:
        response = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
        response.raise_for_status()
        return tuple(model["name"] for model in response.json().get("models", []))

    def generate(self, model: str, prompt: str, *, system: str = "",
                 num_predict: int = 128, temperature: float = 0.0) -> str:
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "think": False,
                   "options": {"num_predict": num_predict,
                                "temperature": temperature}}
        if system:
            payload["system"] = system
        response = httpx.post(f"{self.base_url}/api/generate", json=payload,
                              timeout=self.timeout)
        response.raise_for_status()
        text = str(response.json().get("response", "")).strip()
        if not text:
            raise OllamaError(f"Ollama returned an empty response for {model}")
        return text


class OllamaRouter:
    """Selects, executes, and learns model choices from real outcomes."""

    def __init__(self, profiles: tuple[ModelProfile, ...],
                 *, client: OllamaClient | None = None,
                 state_path: str | Path | None = None):
        if not profiles:
            raise ValueError("at least one model profile is required")
        self.profiles = {profile.name: profile for profile in profiles}
        if len(self.profiles) != len(profiles):
            raise ValueError("model names must be unique")
        self.client = client or OllamaClient()
        self.state_path = Path(state_path) if state_path is not None else None
        self._success = {name: 0 for name in self.profiles}
        self._failure = {name: 0 for name in self.profiles}
        self._load_state()

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        for name in self.profiles:
            self._success[name] = int(data.get("success", {}).get(name, 0))
            self._failure[name] = int(data.get("failure", {}).get(name, 0))

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "success": self._success, "failure": self._failure}
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.state_path)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", text.lower()))

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _score(self, query: set[str], profile: ModelProfile) -> float:
        overlap = len(query.intersection(profile.tags))
        trials = self._success[profile.name] + self._failure[profile.name]
        posterior = (self._success[profile.name] + 1) / (trials + 2)
        return 2 * overlap + posterior

    def _rank(self, prompt: str) -> list[ModelProfile]:
        tokens = self._tokens(prompt)
        return sorted(self.profiles.values(),
                      key=lambda profile: (-self._score(tokens, profile), profile.name))

    def generate(self, prompt: str, *, max_attempts: int | None = None,
                 num_predict: int = 128, system: str = "") -> GenerationResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        ranked = self._rank(prompt)
        limit = max_attempts or len(ranked)
        attempts: list[str] = []
        last_error: str | None = None
        started = time.perf_counter()
        for profile in ranked[:limit]:
            attempts.append(profile.name)
            try:
                text = self.client.generate(profile.name, prompt, system=system,
                                            num_predict=num_predict)
            except Exception as exc:  # backend failures are typed in the result
                self._failure[profile.name] += 1
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            self._success[profile.name] += 1
            self._save_state()
            return GenerationResult(
                profile.name, text, "succeeded",
                (time.perf_counter() - started) * 1000.0, tuple(attempts))
        self._save_state()
        return GenerationResult(
            attempts[-1] if attempts else "", "", "failed",
            (time.perf_counter() - started) * 1000.0, tuple(attempts), last_error)