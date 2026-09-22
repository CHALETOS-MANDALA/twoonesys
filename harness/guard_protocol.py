"""CASCADE - Integrazione: protocollo Z3 in tre passi (LBP2_CONTRATTI_V1 §7).

Il difetto che corregge: una verifica del tipo `premesse ∧ ¬regole → unsat =>
approva` e' NECESSARIA ma INCOMPLETA. Se le premesse sono contraddittorie,
quella formula e' insoddisfacibile per VACUITA' e il guard approva. Caso
misurato nei doc:

   coerent, rispetta (30 <= 50)     -> REGOLE VERIFICATE
   coerente, viola   (90 <= 50)     -> VIOLAZIONE (+ controesempio)
   CONTRADDITTORIE  (velocita=30 ∧ velocita=90, limite=50)
       correzione ingenua:            APPROVA        <- fail-open
       protocollo a 3 passi:          INVALID_CONTEXT

Protocollo corretto:
    A. Validare schema, tipi e binding richiesti
         simbolo dichiarato ma non fornito   -> missing_binding (errore duro)
    B. Consistenza delle premesse:   Solver(premesse).check()
         sat      -> prosegui
         unsat    -> INVALID_CONTEXT     (mai Permit)
         unknown  -> INDETERMINATE       (mai Permit)
    C. Ricerca della violazione:     Solver(premesse ∧ ¬regole).check()
         sat      -> VIOLAZIONE + controesempio
         unsat    -> regole verificate SOTTO QUELLE PREMESSE
         unknown  -> INDETERMINATE       (mai Permit)

missing_binding, timeout e unknown NON diventano mai un via libera. E quello
che il protocollo da' e' solo l'esito SIMBOLICO: RULES_VERIFIED non e' un
permesso di esecuzione. A valle servono SEMPRE i contratti v1
(contracts_v1.Authorization): una prova (ne' una probabilita') autorizza
implicitamente.

Questo modulo e' UN'INTEGRAZIONE: riusa SymbolicContract e _to_z3 da
neurosymbolic_guard.py senza toccare quel file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

import z3

from .neurosymbolic_guard import SymbolicContract, _to_z3


class GuardStatus(str, Enum):
    RULES_VERIFIED = "rules_verified_under_premises"
    VIOLATION = "violation"
    INVALID_CONTEXT = "invalid_context"
    MISSING_BINDING = "missing_binding"
    INVALID_CONFIG = "invalid_config"     # es. guard senza regole: mai un via libera
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class GuardVerdict:
    """Esito tipizzato del protocollo. `proceed` e' True SOLO se RULES_VERIFIED."""
    status: GuardStatus
    message: str
    counterexample: dict[str, Any] | None = None

    @property
    def proceed(self) -> bool:
        """Mai un via libera per contesti non validi, binding mancanti o ignoti."""
        return self.status is GuardStatus.RULES_VERIFIED


def _references_symbol(formula: z3.BoolRef, symbol: z3.ExprRef) -> bool:
    """Un binding e' 'fornito' se compare (a qualunque profondita') in una premessa."""
    if formula.eq(symbol):
        return True
    for child in formula.children():
        if _references_symbol(child, symbol):
            return True
    return False


def _model_counterexample(model: z3.ModelRef,
                          contract: SymbolicContract) -> dict[str, Any]:
    cex: dict[str, Any] = {}
    for name, expr in contract.symbols.items():
        try:
            val = model[expr]
        except (z3.Z3Exception, IndexError, KeyError):
            val = None
        if val is not None:
            cex[name] = val
    return cex


def _check_step(solver: z3.Solver,
                solver_check: Callable[[z3.Solver], z3.CheckSatResult] | None,
                timeout_ms: int | None) -> z3.CheckSatResult:
    if timeout_ms is not None:
        solver.set(timeout=timeout_ms)
    if solver_check is not None:
        return solver_check(solver)
    return solver.check()


def check_contract(contract: SymbolicContract,
                   concrete: Mapping[str, Any],
                   premises: tuple[z3.BoolRef, ...] = (),
                   timeout_ms: int | None = None,
                   solver_check: Callable[[z3.Solver], z3.CheckSatResult] | None = None,
                   ) -> GuardVerdict:
    """Applica il protocollo a 3 passi a UN contratto.

    `concrete` = binding valore->simbolo forniti come dati concreti.
    `premises` = vincoli aggiuntivi (es. velocita==30, velocita==90) che devono
    essere consistenti PRIMA di qualunque ricerca di violazione.
    `solver_check` = seam per i test (iniettabile per simulare unknown/unknown).
    """
    declared = set(contract.symbols)
    bound = set(concrete)

    # -- PASSI A: schema, tipi e binding richiesti --------------------------- #
    provided = bound | {
        name for name, expr in contract.symbols.items()
        if any(_references_symbol(p, expr) for p in premises)
    }
    missing = declared - provided
    if missing:
        return GuardVerdict(
            GuardStatus.MISSING_BINDING,
            f"binding richiesto non fornito: {', '.join(sorted(missing))}")

    # quantifica i binding concreti come premesse (errore di tipo = hard)
    bound_premises: list[z3.BoolRef] = []
    for name, value in concrete.items():
        if name not in contract.symbols:
            continue
        try:
            bound_premises.append(contract.symbols[name] == _to_z3(value))
        except TypeError as exc:
            return GuardVerdict(
                GuardStatus.MISSING_BINDING,
                f"binding non tipizzabile per Z3: {name} ({exc})")
    all_premises = list(premises) + bound_premises

    # -- PASSO B: consistenza delle premesse --------------------------------- #
    b_solver = z3.Solver()
    for p in all_premises:
        b_solver.add(p)
    res = _check_step(b_solver, solver_check, timeout_ms)
    if res == z3.unsat:
        return GuardVerdict(
            GuardStatus.INVALID_CONTEXT,
            "premesse contraddittorie: nessuna azione e' nemmeno coerentemente "
            "descritta")
    if res == z3.unknown:
        return GuardVerdict(
            GuardStatus.INDETERMINATE,
            "solver: consistenza delle premesse sconosciuta (timeout/unknown)")

    # -- PASSO C: ricerca della violazione ----------------------------------- #
    c_solver = z3.Solver()
    for p in all_premises:
        c_solver.add(p)
    if contract.expressions:
        c_solver.add(z3.Not(z3.And(*contract.expressions)))
    res = _check_step(c_solver, solver_check, timeout_ms)
    if res == z3.sat:
        model = c_solver.model()
        return GuardVerdict(
            GuardStatus.VIOLATION,
            f"contratto '{contract.name}' violato sotto quelle premesse",
            counterexample=_model_counterexample(model, contract))
    if res == z3.unknown:
        return GuardVerdict(
            GuardStatus.INDETERMINATE,
            "solver: ricerca della violazione sconosciuta (timeout/unknown)")
    return GuardVerdict(
        GuardStatus.RULES_VERIFIED,
        f"regole del contratto '{contract.name}' verificate sotto quelle premesse")


# --------------------------------------------------------------------------- #
# Valutazione aggregata su tutti i contratti di un guard
# --------------------------------------------------------------------------- #
# L'ordine di precedenza: qualunque binding mancante, premesse inconsistenti o
# esito sconosciuto fa saltare TUTTO (mai violate le altre regole). Solo se
# nessuno di questi c'e', emergono le violazioni; e solo se non ci sono
# violazioni il verdetto complessivo e' RULES_VERIFIED.

_DEADLY_ORDER = (
    GuardStatus.MISSING_BINDING,
    GuardStatus.INVALID_CONTEXT,
    GuardStatus.INVALID_CONFIG,
    GuardStatus.INDETERMINATE,
    GuardStatus.VIOLATION,
)


def check_all(contracts: list[SymbolicContract],
              concrete: Mapping[str, Any],
              premises: tuple[z3.BoolRef, ...] = (),
              timeout_ms: int | None = None,
              solver_check: Callable[[z3.Solver], z3.CheckSatResult] | None = None,
              ) -> GuardVerdict:
    best: GuardVerdict | None = None
    for contract in contracts:
        v = check_contract(contract, concrete, premises, timeout_ms, solver_check)
        if best is None or _rank(v.status) < _rank(best.status):
            best = v
    if best is None:
        return GuardVerdict(
            GuardStatus.INVALID_CONFIG,
            "nessun contratto da verificare: un via libera senza regole non esiste")
    return best


def _rank(status: GuardStatus) -> int:
    """Minore = piu' severo. Oltre i deadly, RULES_VERIFIED e' il migliore."""
    return _DEADLY_ORDER.index(status) if status in _DEADLY_ORDER else len(_DEADLY_ORDER)


# --------------------------------------------------------------------------- #
# Verifica del verificatore: il via libera non ha buchi + margine
# --------------------------------------------------------------------------- #
# L'esito RULES_VERIFIED dice "nessuna violazione TROVATA". Questa sezione fa
# il check duale: sul modello testimone soddisfacente (premesse + TUTTE le
# regole), ogni vincolo deve valutare Vero, e per i vincoli numerici calcola
# il MARGINE: quanto il mondo certificato e' distante dalla violazione. Un
# green light al confine (margine piccolo) e' bassa garanzia nel mondo: gli
# errori di misura bastano a rovesciarlo. `ok=True` con `margin=None` = le
# regole tengono ma NON c'e' una distanza numerica nota: mai un "sicuro".


@dataclass(frozen=True)
class WitnessCheck:
    ok: bool                       # False = il "via libera" e' bucato
    margin: float | None = None    # minima distanza dal violare una regola
    checks: tuple[tuple[str, bool], ...] = ()
    message: str = ""


def _model_value(expr: z3.ExprRef, model: z3.ModelRef) -> float | None:
    m = model.eval(expr, model_completion=True)
    if m is None:
        return None
    try:
        if z3.is_int_value(m):
            return float(m.as_long())
        if z3.is_rational_value(m):
            return float(m.numerator_as_long()) / float(m.denominator_as_long())
    except (z3.Z3Exception, AttributeError, TypeError):
        return None
    return None


def _numeric_margin(rule: z3.BoolRef, model: z3.ModelRef) -> float | None:
    """Distanza dalla violazione per vincoli di confronto numerico. Regole
    booleane pure o uguaglianze NON danno margine: ritorna None (ignoto).
    Un Not di livello singolo (z3.Not(v > lim) == v <= lim) viene risolto."""
    negate = False
    inner = rule
    if rule.decl().name() == "not" and rule.num_args() == 1:
        negate = True
        inner = rule.arg(0)
    # contratto multi-condizione: ogni congiunto da' un margine, conta il minimo
    if inner.decl().name() == "and" and inner.num_args() > 1:
        parts = [_numeric_margin(inner.arg(i), model)
                 for i in range(inner.num_args())]
        parts = [m for m in parts if m is not None]
        return min(parts) if parts else None
    name = inner.decl().name()
    if name not in ("<=", "<", ">=", ">"):
        return None
    lhs = _model_value(inner.arg(0), model)
    rhs = _model_value(inner.arg(1), model)
    if lhs is None or rhs is None:
        return None
    gap = (rhs - lhs) if name in ("<=", "<") else (lhs - rhs)
    return -gap if negate else gap


def verify_witness(contracts: list[SymbolicContract],
                   concrete: Mapping[str, Any],
                   premises: tuple[z3.BoolRef, ...] = (),
                   timeout_ms: int | None = None,
                   solver_check: Callable[[z3.Solver], z3.CheckSatResult] | None = None,
                   ) -> WitnessCheck:
    """Riapre un solver su premesse ∧ TUTTE le regole e verifica sul modello.

    Chiamare SOLO quando check_all/check_contract ha detto RULES_VERIFIED:
    se le premesse fossero inconsistenti, sat fallisce e `ok=False` (mai un
    via libera su un mondo inesistente). Il margine e' la minima distanza dal
    violare una regola numerica; `None` quando una regola non e' numerica.
    """
    all_rules = [(c, e) for c in contracts for e in c.expressions]
    bound_premises: list[z3.BoolRef] = []
    for contract in contracts:
        for name, value in concrete.items():
            if name not in contract.symbols:
                continue
            try:
                bound_premises.append(contract.symbols[name] == _to_z3(value))
            except TypeError:
                continue
    solver = z3.Solver()
    for p in list(premises) + bound_premises:
        solver.add(p)
    for _, e in all_rules:
        solver.add(e)
    res = _check_step(solver, solver_check, timeout_ms)
    if res != z3.sat:
        return WitnessCheck(
            ok=False, message="solver sul modello testimone: sat fallito/ignoto")
    model = solver.model()

    checks: list[tuple[str, bool]] = []
    margin: float | None = None
    for contract, rule in all_rules:
        val = model.eval(rule, model_completion=True)
        holds = bool(z3.is_true(val))
        checks.append((f"{contract.name}.{len(checks)}", holds))
        if not holds:
            return WitnessCheck(
                ok=False, checks=tuple(checks),
                message=f"regola '{contract.name}' FALSA sul modello testimone: "
                        "il via libera e' bucato")
        m = _numeric_margin(rule, model)
        if m is not None and (margin is None or m < margin):
            margin = max(0.0, m)

    if not all_rules:
        return WitnessCheck(ok=True, checks=tuple(checks),
                            message="nessuna regola da verificare")
    return WitnessCheck(ok=True, margin=margin, checks=tuple(checks),
                        message="tutte le regole valgono sul modello testimone")