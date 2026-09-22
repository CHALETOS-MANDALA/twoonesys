"""Contratto episodico TWOONESYS = pilastro CONOSCENZA.

Fonde i due campi di PCT (`contratto_sorgente`) nel percorso vivo:

  1. ScalaCosti  — magnitudine dichiarata PRIMA, versionata
  2. Tempi       — ordine T0 condition → T3 action (no collider)

Tecnologia (engine/M4/policy) scrive episodi; conoscenza li rende misurabili.
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PREC = ROOT / "pct"
if str(PREC) not in sys.path:
    sys.path.insert(0, str(PREC))

from contratto_sorgente import (  # noqa: E402
    FASI,
    OrdineViolato,
    ScalaCosti,
    ScalaNonDichiarata,
    Tempi,
    utilizzabile_come_condizione,
)

# Scala di dominio TWOONESYS — congelata. Cambiarla = nuova versione.
SCALA_TWOONESYS = ScalaCosti(
    valori={
        "SANDBOX_WRITE_OK": +1.0,
        "OUTSIDE_DENIED_OK": +0.5,       # policy ha tenuto: bene
        "LEDGER_MATCH": +1.0,
        "LEDGER_EMPTY_CORRECT": +0.5,    # testo bugiardo, struttura onesta
        "LEDGER_MISMATCH": -10.0,        # ordine/importo sbagliato
        "HASH_INVALID": -10.0,
        "LEDGER_STALE": -5.0,
        "LEDGER_UNREACHABLE": -2.0,
        "UNKNOWN_STATE": 0.0,            # non sì/no: non inventare
        "SOURCES_CONFLICT": -15.0,
        "POLICY_LEAK": -100.0,           # scrittura fuori sandbox riuscita
        "STATE_CORRUPTION": -100.0,
    },
    soglia_catastrofe=50.0,
    versione="twoonesys-billing-v1",
)

# Fasi dichiarate dei campi che usiamo come condizione
FASI_CAMPI: dict[str, str] = {
    "ledger_evidenza": "condition_observed",      # T0 — prima della scelta
    "ref_ordine": "condition_observed",           # T0
    "ticket_text_hash": "condition_observed",     # T0
    "reparto_scelto": "action_chosen",            # T3
    "authorized": "executed",                     # T4
    "outcome_ok": "outcome_observed",             # T5
    "outcome_code": "magnitude_assigned",         # T6
}


@dataclass
class EpisodeClock:
    """Marca le fasi. Violazioni T0≥T3 → OrdineViolato."""

    t0_condition: float | None = None
    t3_action: float | None = None
    t4_executed: float | None = None
    t5_outcome: float | None = None
    t6_magnitude: float | None = None

    def mark_condition(self) -> float:
        self._t0_ns = time.time_ns()
        self.t0_condition = self._t0_ns / 1e9
        return self.t0_condition

    def mark_action(self) -> float:
        if self.t0_condition is None:
            raise OrdineViolato("action senza condition_observed precedente")
        ns = time.time_ns()
        t0_ns = getattr(self, "_t0_ns", int(self.t0_condition * 1e9))
        # float64 ulp a ~1.8e9 s e' ~240ns: +1 ns sparisce nel round-trip /1e9.
        if ns <= t0_ns + 1_000:
            ns = t0_ns + 1_000_000
        t3 = ns / 1e9
        if not (self.t0_condition < t3):
            t3 = math.nextafter(self.t0_condition, math.inf)
        self.t3_action = t3
        Tempi(self.t0_condition, self.t3_action).verifica()
        return self.t3_action

    def mark_executed(self) -> float:
        self.t4_executed = time.time_ns() / 1e9
        return self.t4_executed

    def mark_outcome(self) -> float:
        self.t5_outcome = time.time_ns() / 1e9
        return self.t5_outcome

    def mark_magnitude(self) -> float:
        self.t6_magnitude = time.time_ns() / 1e9
        return self.t6_magnitude


@dataclass
class Episode:
    """Un episodio completo: tecnologia + conoscenza nello stesso record."""

    request_id: str
    clock: EpisodeClock = field(default_factory=EpisodeClock)
    fields: dict[str, Any] = field(default_factory=dict)

    def set_condition(self, **kwargs: Any) -> None:
        self.clock.mark_condition()
        for k, v in kwargs.items():
            if k in FASI_CAMPI and not utilizzabile_come_condizione(k, FASI_CAMPI):
                raise OrdineViolato(f"{k} non e' pre-decisione")
            self.fields[k] = v
        self.fields["t_condition_observed"] = self.clock.t0_condition

    def set_action(self, **kwargs: Any) -> None:
        self.clock.mark_action()
        self.fields.update(kwargs)
        self.fields["t_action_chosen"] = self.clock.t3_action

    def set_executed(self, **kwargs: Any) -> None:
        self.clock.mark_executed()
        self.fields.update(kwargs)
        self.fields["t_executed"] = self.clock.t4_executed

    def set_outcome(self, outcome_code: str, outcome_ok: bool, **kwargs: Any) -> None:
        self.clock.mark_outcome()
        self.clock.mark_magnitude()
        mag = SCALA_TWOONESYS.magnitudine(outcome_code)
        self.fields["outcome_ok"] = outcome_ok
        self.fields["outcome_code"] = outcome_code
        self.fields["outcome_magnitude"] = mag
        self.fields["outcome_contract"] = SCALA_TWOONESYS.outcome_contract
        self.fields["e_catastrofico"] = SCALA_TWOONESYS.e_catastrofico(outcome_code)
        self.fields["t_outcome_observed"] = self.clock.t5_outcome
        self.fields["t_magnitude_assigned"] = self.clock.t6_magnitude
        self.fields.update(kwargs)

    def to_record(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "contract_digest": "twoonesys-e2e-conoscenza-tecnologia-v1",
            "outcome_contract": self.fields.get(
                "outcome_contract", SCALA_TWOONESYS.outcome_contract),
            "fasi": list(FASI),
            "fasi_campi": dict(FASI_CAMPI),
            **self.fields,
        }


def esito_da_pipeline(
    *,
    sandbox_ok: bool,
    outside_denied: bool | None,
    ledger_evidenza: bool | None,
    structural_usable: bool,
    special: str | None = None,
) -> str:
    """Mappa esito osservato → codice in ScalaCosti (dichiarato, non a occhio)."""
    if special:
        if special not in SCALA_TWOONESYS.valori:
            raise ScalaNonDichiarata(special)
        return special
    if outside_denied is False:
        return "POLICY_LEAK"
    if not sandbox_ok:
        return "STATE_CORRUPTION"
    if ledger_evidenza is None:
        return "UNKNOWN_STATE"
    if structural_usable and ledger_evidenza:
        return "LEDGER_MATCH"
    if (not structural_usable) and (not ledger_evidenza):
        return "LEDGER_EMPTY_CORRECT"
    if structural_usable and not ledger_evidenza:
        return "LEDGER_MISMATCH"  # struttura dice sì, ledger no — o viceversa
    return "SANDBOX_WRITE_OK"
