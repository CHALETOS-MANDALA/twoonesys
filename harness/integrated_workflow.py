"""End-to-end CASCADE workflow: model proposal, evidence, verification, action."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import sha256_hex
from .ollama_router import GenerationResult, OllamaRouter
from .outcome_log import OutcomeLog, OutcomeRecord
from .workers import ChainReport, parse_model_claim_value, run_verified


@dataclass(frozen=True)
class WorkflowResult:
    request_id: str
    generation: GenerationResult
    evidence: ChainReport
    action_status: str
    action_receipt: str | None
    elapsed_ms: float


class IntegratedWorkflow:
    """Coordinates real model output with deterministic evidence and action."""

    def __init__(self, router: OllamaRouter, *, log: OutcomeLog,
                 action_root: str | Path):
        self.router = router
        self.log = log
        self.action_root = Path(action_root).resolve()
        self.action_root.mkdir(parents=True, exist_ok=True)

    def run(self, request_id: str, prompt: str, docs: list[str], *, n: int = 1,
            executor: Callable[[Path, str], str] | None = None,
            action_chosen: str | None = None,
            model_value: str | None = None) -> WorkflowResult:
        started = time.perf_counter()
        generation = self.router.generate(prompt, num_predict=64)
        return self._complete(request_id, prompt, docs, n, executor, generation,
                              raw_confidence=0.5,
                              action_chosen=action_chosen,
                              model_value=model_value)

    def run_with_latent_brain(self, request_id: str, prompt: str,
                              docs: list[str], brain: Any, *, n: int = 1,
                              user_feedback: float | None = None,
                              selection_probability: float = 1.0,
                              label_source: str = "mechanical",
                              action_chosen: str | None = None,
                              model_value: str | None = None,
                              executor: Callable[[Path, str], str] | None = None) -> WorkflowResult:
        """Runs CASCADE using a real Latent Brain+ proposal as input."""
        started = time.perf_counter()
        proposal = brain.propose(prompt, user_feedback=user_feedback)
        generation = GenerationResult(
            model="latent-brain-plus", text=proposal.text, status="succeeded",
            latency_ms=proposal.latency_seconds * 1000.0,
            attempts=("latent-brain-plus",))
        return self._complete(request_id, prompt, docs, n, executor, generation,
                              raw_confidence=proposal.confidence,
                              started=started,
                              selection_probability=selection_probability,
                              label_source=label_source,
                              action_chosen=action_chosen,
                              model_value=model_value or parse_model_claim_value(proposal.text))

    def run_with_rizzo(self, request_id: str, prompt: str,
                       docs: list[str], proposer: Any, *,
                       state: Any, questions: dict,
                       question: str | None = None,
                       n: int = 1,
                       selection_probability: float = 1.0,
                       label_source: str = "mechanical",
                       executor: Callable[[Path, str], str] | None = None) -> WorkflowResult:
        """Runs CASCADE using a TWOONESYS engine (Rizzo Flow) proposal as input.

        Differenza decisiva rispetto agli altri proponenti: la confidenza e'
        la probabilita' del valore scelto letta dai logit (0 token generati),
        e l'identita' del braccio e' la decisione stessa.

        Astensione dell'engine (status != "ok"): generation.status NON e'
        "succeeded", quindi il gate resta chiuso e il record conserva il
        perche'. Un'astensione non viene MAI autorizzata.
        """
        started = time.perf_counter()
        proposal = proposer.propose(state, questions, question=question)
        generation = GenerationResult(
            model=proposal.model_id,
            text=proposal.value or f"__abstained__:{proposal.status}",
            status=("succeeded" if not proposal.abstained
                    else f"abstained:{proposal.status}"),
            latency_ms=proposal.latency_ms,
            attempts=(proposal.model_id,))
        return self._complete(request_id, prompt, docs, n, executor, generation,
                              raw_confidence=proposal.confidence,
                              started=started,
                              selection_probability=selection_probability,
                              label_source=label_source,
                              action_chosen=proposal.value,
                              model_value=proposal.model_value)

    def _complete(self, request_id: str, prompt: str, docs: list[str], n: int,
                  executor: Callable[[Path, str], str] | None,
                  generation: GenerationResult, *, raw_confidence: float,
                  started: float | None = None,
                  selection_probability: float | None = None,
                  label_source: str | None = None,
                  action_chosen: str | None = None,
                  model_value: str | None = None) -> WorkflowResult:
        """Run one decision end-to-end.

        `approved` = gate ha autorizzato l'esecuzione (Evidence + Policy passati).
        `outcome`   = l'esecuzione ha SUCCESSO (reale, mai derivato da `approved`).
        I due campi sono ORIGINATI DA FONTI DIVERSE: il gate da Evidence/verification,
        l'esito dall'executor esterno. Non sono mai la stessa cosa.
        """
        started = time.perf_counter() if started is None else started
        query = f"{prompt} {generation.text}" if generation.text else prompt
        typed = model_value or parse_model_claim_value(generation.text)
        evidence = run_verified(
            query, docs, calc_kind="zeron", calc_args={"n": n},
            model_value=typed)
        # gate: autorizza se prove sufficienti E verifica OK
        gate_approved = (generation.status == "succeeded"
                         and evidence.verdict.ok)
        action_status = "blocked"
        receipt = None
        if gate_approved:
            target = (self.action_root / f"{request_id}.json").resolve()
            if self.action_root not in target.parents:
                raise ValueError("action target escaped action root")
            payload = json.dumps({"request_id": request_id,
                                  "model": generation.model,
                                  "evidence": evidence.subject_id,
                                  "response": generation.text}, sort_keys=True)
            writer = executor or self._write_action
            try:
                receipt = writer(target, payload)
                action_status = "succeeded"
            except Exception:
                action_status = "failed"
        # esito OSSERVATO dall'executor (mai derivato dal gate)
        outcome = (action_status == "succeeded")
        # identita' del braccio: serve per IPS/doubly-robust (§4.3 problema 1)
        chosen = action_chosen or generation.model or "verified_model_action"
        # approved = gate di autorizzazione (separato dall'esito osservato)
        # outcome = esecuzione osservata (reale, mai derivato)
        self.log.record(OutcomeRecord(
            request_id=request_id,
            action="verified_model_action",
            action_chosen=chosen,
            raw_confidence=max(0.0, min(1.0, float(raw_confidence))),
            measured_p=None,
            escalated=not evidence.verdict.ok,
            approved=gate_approved,     # gate separato dall'outcome
            outcome=outcome,            # osservazione reale
            touched=time.time(),
            contract_digest="integrated-workflow-v1",
            label_source=label_source,
            selection_probability=selection_probability))
        return WorkflowResult(request_id, generation, evidence, action_status,
                              receipt, (time.perf_counter() - started) * 1000.0)

    @staticmethod
    def _write_action(target: Path, payload: str) -> str:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(target)
        return sha256_hex({"path": str(target), "payload": payload})