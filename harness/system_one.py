"""CASCADE - Passo 7: il circuito CHIUSO del System One, end-to-end.

L'audit (AUDIT_FINALE_2026-09-17): "il pezzo mancante e' un modulo da
centoventi righe, piu' la disciplina di registrare gli esiti". Gli strumenti
ci sono (ReliabilityMeter misura, ConformalCalibrator copre, ShadowEscalation
registra l'escalation del System 2, azione_autorizza esegue coi Permit):
questo modulo LI CABLA nel circuito chiuso dove la confidenza che decide il
gate NON e' piu' quella auto-dichiarata dall'agente, ma quella MISURATA.

Il giro:

     agente dichiara conf_raw            ->  raw_confidence
     ReliabilityMeter.calibrate(conf)    ->  measured_p      (solo con storia)
     readout + policy (>= 1-alpha)       ->  escalate?       (escalation ombra)
     dispose: system_two / Permit + grant anti-TOCTOU + executor
     esito reale (Succeeded/Failed/Indeterminate)
     settle: esito -> meter.record+fit + OutcomeLog (persistente)

Regole di onesta':
* COLD START SENZA VIA LIBERA: senza misura (< min_samples) `measured_p=None`
  e il rischio e' massimo -> SEMPRE escalation; mai un proceed senza storia.
* `outcome` Indeterminate NON alimenta il misuratore (stato ignoto != esito).
* Nessun numero inventato: estimate CalibratedEstimate nasce SOLO da una
  curva; altrimenti `estimate=None`.
* L'esecuzione passa SEMPRE per `azione_autorizza` (permit + grant + recheck
  atomico): il loop non esegue mai "direttamente".

Dipendenze: moduli propri (reliability, conformal, escalation, contracts_v1,
action_authorize, outcome_log). Nessuna modifica ai moduli esistenti.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .action_authorize import GrantRegistry, azione_autorizza
from .contracts_v1 import (
    CalibratedEstimate,
    CalibrationPolicy,
    ExecutionResult,
    Failed,
    Indeterminate,
    Permit,
    ProbabilityThreshold,
    Succeeded,
    contract_digest,
)
from .escalation import EscalationReason, ShadowEscalation, SystemOneReadout
from .guard_protocol import GuardVerdict, check_all, verify_witness, WitnessCheck
from .neurosymbolic_guard import SymbolicContract
from .outcome_log import OutcomeLog, OutcomeRecord, replay_all
from .reliability import ReliabilityMeter

CALIB_EVENT = "outcome.success"
CALIB_DIGEST = contract_digest(calibrator="reliability_pav", event=CALIB_EVENT)

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "run" / "outcome_log.jsonl"


@dataclass(frozen=True)
class Assessment:
    """Lettura calibrata del percorso primario per UN caso."""
    request_id: str
    action: str
    raw_confidence: float                    # cio' che l'agente ha dichiarato
    readout: SystemOneReadout
    estimate: CalibratedEstimate | None      # None = nessuna misura, mai inventato
    escalate: bool
    reason: EscalationReason
    risk: float
    escalation_index: int


class SystemOneLoop:
    """Il circuito chiuso: misura -> gate calibrato -> decide -> esegue -> registra."""

    def __init__(self, *, meter: ReliabilityMeter | None = None,
                 conformal: Any | None = None,
                 shadow: ShadowEscalation | None = None,
                 log: OutcomeLog | None = None,
                 alpha: float = 0.10,
                 target_event: str = CALIB_EVENT,
                 action_class: str = "auto"):
        self.meter = meter or ReliabilityMeter()
        self.conformal = conformal            # opzionale: ConformalCalibrator
        self.shadow = shadow or ShadowEscalation(alpha=float(alpha))
        # la disciplina E' ON per default: senza log esplicita si registra su
        # cascade/run/outcome_log.jsonl (l'audit: registrare gli esiti, sempre).
        self.log = log if log is not None else OutcomeLog(DEFAULT_LOG_PATH)
        self.alpha = float(alpha)
        self.policy = CalibrationPolicy(
            target_event=target_event, action_class=action_class,
            applicable_digests=frozenset({CALIB_DIGEST}))
        self.threshold = ProbabilityThreshold(
            value=1.0 - self.alpha, target_event=target_event,
            action_class=action_class)
        if self.meter.size:
            self.meter.fit()

    # ------------------------------------------------------------------ #
    # costruzione dal registro persistente (il "restart")
    # ------------------------------------------------------------------ #
    @classmethod
    def from_log(cls, path, *, alpha: float = 0.10,
                 action_class: str = "auto") -> "SystemOneLoop":
        """Riapre la log e RICOSTRUISCE misuratore e stato, identici."""
        log, meter = replay_all(path)
        return cls(meter=meter, log=log, alpha=alpha, action_class=action_class)

    # ------------------------------------------------------------------ #
    # passo 1: ASSESS — la lettura calibrata (read-only, tap in ombra)
    # ------------------------------------------------------------------ #
    def assess(self, request_id: str, action: str, raw_confidence: float,
               *, conformal_risk: float | None = None) -> Assessment:
        raw = float(raw_confidence)
        measured_p = self._measure(raw)
        estimate = None
        if measured_p is not None:
            estimate = CalibratedEstimate(value=measured_p,
                                          target_event=self.policy.target_event,
                                          contract_digest=CALIB_DIGEST)
        risk = self._risk(conformal_risk, measured_p)
        escalate, reason = self._escalate(risk, measured_p)
        readout = SystemOneReadout(proceed=not escalate, risk=risk,
                                   measured_p=measured_p, score=risk)
        self.shadow.observe(readout)          # osservazione in ombra (nessun side-effect)
        return Assessment(request_id=request_id, action=action,
                          raw_confidence=raw,
                          readout=readout, estimate=estimate,
                          escalate=escalate, reason=reason, risk=risk,
                          escalation_index=len(self.shadow.records()) - 1)

    def _measure(self, raw: float) -> float | None:
        if self.meter.size < self.meter.min_samples:
            return None                       # nessuna curva onesta: mai inventare
        return float(self.meter.calibrate(raw))

    def _risk(self, conformal_risk: float | None, measured_p: float | None) -> float:
        if conformal_risk is not None:
            return max(0.0, min(1.0, float(conformal_risk)))
        if measured_p is not None:
            return 1.0 - measured_p
        return 1.0                            # nessuna misura: rischio massimo

    def _escalate(self, risk: float,
                  measured_p: float | None) -> tuple[bool, EscalationReason]:
        if risk >= self.alpha:
            return True, EscalationReason.HIGH_RISK
        if measured_p is not None and measured_p < 1.0 - self.alpha:
            return True, EscalationReason.LOW_CONFIDENCE
        return False, EscalationReason.NO_SIGNAL

    # ------------------------------------------------------------------ #
    # passo 2: DISPOSE — escalation/System 2, poi autorizzazione+esecuzione
    # ------------------------------------------------------------------ #
    def dispose(self, assessment: Assessment, *,
                system_two: Callable[[], bool | None] | None = None,
                registry: GrantRegistry | None = None,
                permit: Permit | None = None,
                grant_doc: Any = None,
                tool: str = "",
                scope: str = "",
                params: Mapping[str, Any] | None = None,
                state: Mapping[str, Any] | None = None,
                executor: Callable[[dict[str, Any]], Any] | None = None,
                timeout_ms: int | None = None) -> tuple[ExecutionResult, bool]:
        """Risolve il caso: escalation o esecuzione protetta.

        Ritorna (esito, eseguito_davvero). L'esecuzione passa SEMPRE per
        azione_autorizza; senza guardia/permesso/grant/registro l'esito e'
        Indeterminate (mai un proseguimento di comodo).
        """
        if assessment.escalate:
            if system_two is None:
                return Indeterminate(f"reconcile:system_two:{assessment.request_id}"), False
            try:
                supported = bool(system_two())
            except Exception:                 # noqa: BLE001
                supported = None
            if supported is not True:
                return Failed("system_two_non_approva"), False
        if registry is None or permit is None or grant_doc is None:
            return Indeterminate(
                f"reconcile:no_authorization:{assessment.request_id}"), False
        res = azione_autorizza(
            registry, permit, grant_doc, tool=tool, scope=scope,
            params=dict(params or {}), state=dict(state or {}),
            executor=executor, timeout_ms=timeout_ms)
        return res, isinstance(res, Succeeded)

    # ------------------------------------------------------------------ #
    # passo 3: SETTLE — l'esito reale chiude il circuito
    # ------------------------------------------------------------------ #
    def settle(self, assessment: Assessment, result: ExecutionResult,
               *, outcome: bool | None = None,
               action_chosen: str | None = None,
               selection_probability: float | None = None,
               contract_digest: str = "",
               label_source: str | None = None) -> None:
        """Registra l'esito: chiude l'escalation, alimenta il misuratore e la
        log persistente. Indeterminate NON conta come esito (outcome=None)."""
        if outcome is None:
            if isinstance(result, Succeeded):
                outcome = True
            elif isinstance(result, Failed):
                outcome = False
            else:
                outcome = None
        if outcome is not None:
            self.shadow.settle(assessment.escalation_index, bool(outcome))
            self.meter.record(assessment.raw_confidence, bool(outcome))
            self.meter.fit()
        rec = OutcomeRecord(
            request_id=assessment.request_id, action=assessment.action,
            action_chosen=action_chosen,
            raw_confidence=assessment.raw_confidence,
            measured_p=assessment.readout.measured_p,
            escalated=assessment.escalate,
            approved=isinstance(result, Succeeded), outcome=outcome,
            touched=time.time(), selection_probability=selection_probability,
            contract_digest=contract_digest,
            label_source=label_source)
        self.log.record(rec)

    # ------------------------------------------------------------------ #
    # giro completo in una chiamata (per i chiamanti semplici)
    # ------------------------------------------------------------------ #
    def process(self, *, request_id: str, action: str, raw_confidence: float,
                permit: Permit, grant_doc: Any, registry: GrantRegistry,
                tool: str, scope: str, params: Mapping[str, Any],
                state: Mapping[str, Any],
                executor: Callable[[dict[str, Any]], Any],
                system_two: Callable[[], bool | None] | None = None,
                conformal_risk: float | None = None,
                timeout_ms: int | None = None,
                outcome: bool | None = None,
                action_chosen: str | None = None,
                selection_probability: float | None = None,
                contract_digest: str = "",
                label_source: str | None = None) -> tuple[Assessment, ExecutionResult]:
        a = self.assess(request_id, action, raw_confidence,
                        conformal_risk=conformal_risk)
        res, _ = self.dispose(a, system_two=system_two, registry=registry,
                              permit=permit, grant_doc=grant_doc, tool=tool,
                              scope=scope, params=params, state=state,
                              executor=executor, timeout_ms=timeout_ms)
        self.settle(a, res, outcome=outcome, action_chosen=action_chosen,
                selection_probability=selection_probability,
                contract_digest=contract_digest, label_source=label_source)
        return a, res

    # ------------------------------------------------------------------ #
    # verifica del verificatore: il via libera del guard non ha buchi
    # ------------------------------------------------------------------ #
    def guard_check(self, contracts: list[SymbolicContract],
                    concrete: Mapping[str, Any],
                    premises: tuple[Any, ...] = ()) -> tuple[GuardVerdict, WitnessCheck]:
        """check_all + verify_witness: il green light certificato con margine."""
        verdict = check_all(contracts, concrete, premises)
        if verdict.status.name != "RULES_VERIFIED":
            return verdict, WitnessCheck(
                ok=False, message=f"verdetto non verde: {verdict.status.value}")
        witness = verify_witness(contracts, concrete, premises)
        return verdict, witness