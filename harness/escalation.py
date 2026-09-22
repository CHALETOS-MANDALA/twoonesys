"""CASCADE - Passo 5: escalation del System 2 IN OMBRA, conformal e propensione.

System One first: il percorso primario (L0 deterministico + gate calibrato)
decide per primo. Quando System One e' incerto, il System 2 (il guard Z3 a 3
passi di guard_protocol) va INVOCATO — ma prima di farlo agire davvero,
l'escalation va MISURATA. Questo modulo E' quella misura: registra le
osservazioni in ombra e ritorna i numeri della politica di escalazione.

Cosa accumula (read-only, nessun side-effect):
    * il readout di System One (proceed conformal, rischio, probabilita'
      misurata da reliability);
    * se servirà l'esito del System 2 (guard Z3) — 'in ombra' significa che
      lo registriamo SENZA modificare il flusso;
    * l'esito reale a posteriori (`settle`), quando il mondo risponde.

Cosa ritorna (onesto, mai inventato):
    * escalation_rate, error_rate_admitted (falsi negativi del percorso
      solo-System-One), system_two_catches, missing_system_two;
    * propensity(risk) = P(escalate | fascia di rischio), empirica sui record
      con smoothing di Laplace; zero record => neutra (propensione a priori).

Scala: `readout` puo' nascere proprio da ConformalCalibrator.decide() e
ReliabilityMeter.calibrate() (conformal.py / reliability.py): qui viene solo
consumato. Il System 2 e' un callable: `system_two()` -> True = appoggia,
False = bloccherebbe, None/eccezione = non ha risposto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class EscalationReason(str, Enum):
    NO_SIGNAL = "no_signal"            # System One procede: nessuna escalazione
    HIGH_RISK = "high_risk"            # risk conformal oltre il livello
    LOW_CONFIDENCE = "low_confidence"  # probabilita' misurata sotto 1-alpha


@dataclass(frozen=True)
class SystemOneReadout:
    """Lettura del percorso primario, gia' calibrata dai layer di fiducia."""
    proceed: bool
    risk: float            # rischio conformal (1 - P(score <= threshold))
    measured_p: float | None = None    # probabilita' misurata (reliability);
                                       # None se il misuratore non ha storia
    score: float = 0.0


@dataclass(frozen=True)
class EscalationRecord:
    escalate: bool
    reason: EscalationReason
    risk: float
    measured_p: float | None
    system_two_supported: bool | None = None   # esito del guard, se eseguito
    success: bool | None = None                # esito reale, quando arriva


class ShadowEscalation:
    """Misura la politica di escalazione senza farla agire."""

    def __init__(self, alpha: float = 0.10, n_risk_bins: int = 8,
                 prior: float = 1.0):
        self.alpha = float(alpha)
        self.n_bins = int(n_risk_bins)
        self.prior = float(prior)
        self._records: list[EscalationRecord] = []

    # ------------------------------------------------------------------ #
    # osservazione
    # ------------------------------------------------------------------ #
    def observe(self, readout: SystemOneReadout,
                system_two: Callable[[], bool | None] | None = None,
                ) -> EscalationRecord:
        """Decide se il System 2 dovrebbe scattare (in ombra) e, se si',
        lo interroga per MISURARE cosa avrebbe detto."""
        escalate, reason = self._escalate(readout)
        supported: bool | None = None
        if escalate and system_two is not None:
            try:
                supported = bool(system_two())
            except Exception:                       # noqa: BLE001
                supported = None                    # guard senza risposta
        rec = EscalationRecord(
            escalate=escalate, reason=reason, risk=readout.risk,
            measured_p=readout.measured_p,
            system_two_supported=supported)
        self._records.append(rec)
        return rec

    def settle(self, idx: int, success: bool) -> None:
        """Registra l'esito reale del caso idx (arrivato a posteriori)."""
        rec = self._records[idx]
        self._records[idx] = EscalationRecord(
            escalate=rec.escalate, reason=rec.reason, risk=rec.risk,
            measured_p=rec.measured_p,
            system_two_supported=rec.system_two_supported, success=bool(success))

    def _escalate(self, readout: SystemOneReadout) -> tuple[bool, EscalationReason]:
        if not readout.proceed:
            return True, EscalationReason.HIGH_RISK
        if (readout.measured_p is not None
                and readout.measured_p < 1.0 - self.alpha):
            return True, EscalationReason.LOW_CONFIDENCE
        return False, EscalationReason.NO_SIGNAL

    # ------------------------------------------------------------------ #
    # propensione (empirica, smooth di Laplace, mai inventata)
    # ------------------------------------------------------------------ #
    def propensity(self, risk: float) -> float:
        """P(escalate | fascia di rischio): empirica sui record osservati,
        con smoothing di Laplace; zero record => propensione a priori ~0."""
        if not self._records:
            return 0.0
        r = max(0.0, min(1.0, float(risk)))
        bucket = min(int(r * self.n_bins), self.n_bins - 1)
        tot = es = 0
        for rec in self._records:
            rb = min(int(max(0.0, min(1.0, rec.risk)) * self.n_bins),
                     self.n_bins - 1)
            if rb == bucket:
                tot += 1
                es += 1 if rec.escalate else 0
        return (es + self.prior) / (tot + 2.0 * self.prior)

    # ------------------------------------------------------------------ #
    # report (l'onesto contatore)
    # ------------------------------------------------------------------ #
    def report(self) -> dict:
        n = len(self._records)
        if n == 0:
            return {"n": 0, "escalated": 0, "escalation_rate": None,
                    "settled": 0, "error_rate_admitted": None,
                    "system_two_catches": None, "missing_system_two": None}

        escalated = [r for r in self._records if r.escalate]
        admitted = [r for r in self._records if not r.escalate]

        settled_esc = [r for r in escalated if r.success is not None]
        settled_adm = [r for r in admitted if r.success is not None]

        errors_admitted = sum(1 for r in settled_adm if not r.success)
        system_two_blocked = sum(
            1 for r in escalated
            if r.system_two_supported is False)
        missing = sum(1 for r in escalated
                      if r.system_two_supported is None)

        return {
            "n": n,
            "escalated": len(escalated),
            "escalation_rate": len(escalated) / n,
            "settled": len(settled_esc) + len(settled_adm),
            "error_rate_admitted": (
                errors_admitted / len(settled_adm) if settled_adm else None),
            "system_two_catches": (
                system_two_blocked / len(escalated) if escalated else None),
            "missing_system_two": (missing / len(escalated) if escalated else None),
        }

    def records(self) -> tuple[EscalationRecord, ...]:
        return tuple(self._records)