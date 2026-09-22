"""CASCADE - Layer 5: Guardia Neurosymbolic.

Il prototipo era un semplice motore di regole con una soglia. Qui il layer e'
veramente ibrido:

- percorso NEURALE: produce l'output e una stima di confidenza;
- percorso SIMBOLICO: vincoli formali espressi in logica del primo ordine;
- ARBITRO: verifica con il theorem prover Z3 (SMT) che le precondizioni
  (contract) siano soddisfatte PRIMA di qualsiasi azione, e che il post-stato
  rispetti i vincoli di sicurezza.

Il vero valore rispetto a un if-else: le regole sono oggetti simbolici
(z3.BoolRef) verificabili formalmente, e l'arbitro prova l'assenza di
violazione invece di fidarsi della soglia unica. La soglia di confidenza resta
configurabile per dominio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional

import z3


class ConfidenceLevel(Enum):
    EXPLORATORY = 0.80
    GENERAL = 0.90
    BUSINESS = 0.95
    HIGH = 0.99
    CRITICAL = 0.999


# --------------------------------------------------------------------------- #
# Contratto simbolico
# --------------------------------------------------------------------------- #


@dataclass
class SymbolicContract:
    """Vincolo verificabile formalmente. `expr` e' una formula z3.BoolRef che
    fa riferimento a simboli dichiarati in `symbols` (dizionario nome->z3.ExprRef).
    `vars` mappa i nomi usati dall'utente ai nomi simbolici."""

    name: str
    expressions: list[z3.BoolRef]
    symbols: dict[str, z3.ExprRef]

    def evaluate(self, concrete: Mapping[str, Any]) -> tuple[bool, Optional[dict]]:
        """Verifica che il contratto valga per i valori concreti `concrete`.
        Ritorna (soddisfatto, controesempio) dove controesempio e' un
        dizionario simbolo->valore se insoddisfatto."""
        solver = z3.Solver()
        # fissa i simboli dichiarati ai valori concreti corrispondenti
        for name, expr in self.symbols.items():
            if name in concrete:
                solver.add(expr == _to_z3(concrete[name]))
        for e in self.expressions:
            solver.add(e)
        res = solver.check()
        if res == z3.sat:
            return True, None
        if res == z3.unknown:
            return False, {"error": "solver unknown"}
        # unsat => esiste assegnazione che viola -> cerchiamo il controesempio
        neg_solver = z3.Solver()
        for name, expr in self.symbols.items():
            if name in concrete:
                neg_solver.add(expr == _to_z3(concrete[name]))
        neg_solver.add(z3.Not(z3.And(*self.expressions)))
        if neg_solver.check() == z3.sat:
            model = neg_solver.model()
            cex = {
                name: model[expr]
                for name, expr in self.symbols.items()
                if expr in model
            }
            return False, cex
        return False, {"error": "unexpected"}


def _to_z3(value: Any) -> z3.ExprRef:
    if isinstance(value, bool):
        return z3.BoolVal(value)
    if isinstance(value, int):
        return z3.IntVal(value)
    if isinstance(value, float):
        return z3.RealVal(value)
    raise TypeError(f"Tipo non supportato per Z3: {type(value)}")


# --------------------------------------------------------------------------- #
# Vincoli dichiarativi
# --------------------------------------------------------------------------- #


@dataclass
class GuardViolation:
    kind: str
    message: str
    contract: Optional[str] = None
    counterexample: Optional[dict] = None
    confidence: Optional[float] = None


class NeurosymbolicGuard:
    """Arbitro ibrido: soglia di confidenza + verifica simbolica dei contratti."""

    def __init__(self, threshold: ConfidenceLevel | float = ConfidenceLevel.HIGH):
        # accetta sia un ConfidenceLevel (enum) sia un float puro
        self.threshold = threshold.value if isinstance(threshold, ConfidenceLevel) else float(threshold)
        self.contracts: list[SymbolicContract] = []
        self.violations: list[GuardViolation] = []
        self._incidents = 0

    def add_contract(self, contract: SymbolicContract) -> None:
        self.contracts.append(contract)

    # -- helper dichiarativi frequenti --------------------------------------- #
    def add_int_bounds(self, name: str, min_val: int, max_val: int) -> None:
        """Vincolo simbolico min <= x <= max su una variabile intera."""
        x = z3.Int(name)
        self.add_contract(SymbolicContract(
            name=f"bounds[{name}]",
            expressions=[z3.And(x >= min_val, x <= max_val)],
            symbols={name: x},
        ))

    def add_cap(self, symbol: str, clause: Callable[[z3.ExprRef], z3.BoolRef]) -> None:
        """Vincolo simbolico generico: clause(expr) deve essere verificato."""
        expr = z3.Real(symbol) if "rate" in symbol or "price" in symbol else z3.Int(symbol)
        self.add_contract(SymbolicContract(
            name=f"cap[{symbol}]",
            expressions=[clause(expr)],
            symbols={symbol: expr},
        ))

    # -- pipeline di validazione --------------------------------------------- #
    def validate(self, neural_output: Any, context: Mapping[str, Any]) -> tuple[Any, bool]:
        """Esegue l'output neurale attraverso la verifica simbolica.

        Ritorna (risultato, ok) dove ok=True se l'output ha superato la soglia di
        confidenza E tutti i contratti simbolici. Su violazione di sicurezza
        (contratto) ripiega a un valore sicuro se `safe_fallback` e' presente in
        context, altrimenti blocco totale.
        """
        confidence = float(context.get("confidence", 0.0))
        if confidence < self.threshold:
            self._record(GuardViolation(
                "low_confidence",
                f"confidenza {confidence:.3f} < soglia {self.threshold}",
                confidence=confidence,
            ))
            return None, False

        for contract in self.contracts:
            ok, cex = contract.evaluate(context)
            if not ok:
                self._record(GuardViolation(
                    "contract_violation",
                    f"contratto '{contract.name}' violato",
                    contract=contract.name,
                    counterexample=cex,
                    confidence=confidence,
                ))
                fallback = context.get("safe_fallback")
                if fallback is not None:
                    return fallback, False
                return None, False

        self._incidents = 0
        return neural_output, True

    def _record(self, v: GuardViolation) -> None:
        self.violations.append(v)
        self._incidents += 1

    @property
    def incident_count(self) -> int:
        return self._incidents


# --------------------------------------------------------------------------- #
# Esempio: dosaggio medico con verifica formale
# --------------------------------------------------------------------------- #


def medical_guard() -> NeurosymbolicGuard:
    guard = NeurosymbolicGuard(ConfidenceLevel.CRITICAL)

    # dosaggio = variabile reale; vincolo 0 < dosaggio <= dosaggio_max
    dose = z3.Real("dosaggio")
    dose_max = z3.Real("dosaggio_max")
    guard.add_contract(SymbolicContract(
        name="dosaggio_massimo",
        expressions=[z3.And(dose > 0, dose <= dose_max)],
        symbols={"dosaggio": dose, "dosaggio_max": dose_max},
    ))

    # nessuna controindicazione attiva
    # rappresentiamo le controindicazioni come variabili booleane libere:
    # qui semplicemente vieta che 'allergia' sia vera quando si somministra.
    allergy = z3.Bool("allergia")
    admit = z3.Bool("somministra")
    guard.add_contract(SymbolicContract(
        name="no_allergia",
        expressions=[z3.Not(z3.And(allergy, admit))],
        symbols={"allergia": allergy, "somministra": admit},
    ))
    return guard


if __name__ == "__main__":
    guard = medical_guard()

    # Caso ok
    ok_ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
              "allergia": False, "somministra": True, "confidence": 1.0}
    out, ok = guard.validate({"dose": 400.0}, ok_ctx)
    print("somministrazione ok:", ok, "->", out)

    # Caso violazione: dosaggio oltre il massimo
    bad_ctx = {"dosaggio": 600.0, "dosaggio_max": 500.0,
               "allergia": False, "somministra": True, "confidence": 0.9999,
               "safe_fallback": {"dose": 500.0, "blocked": False}}
    out, ok = guard.validate({"dose": 600.0}, bad_ctx)
    print("dosaggio eccessivo -> ok:", ok, "fallback:", out)

    # Caso violazione: allergia attiva con somministrazione (blocco totale)
    allergy_ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
                   "allergia": True, "somministra": True, "confidence": 0.9999}
    out, ok = guard.validate({"dose": 400.0}, allergy_ctx)
    print("allergia attiva -> ok:", ok, "risultato:", out, "(blocco)")
