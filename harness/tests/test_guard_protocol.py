"""CASCADE - Integrazione: suite del protocollo Z3 a 3 passi (guard_protocol).

CorrectnessSuite: gli invarianti di sicurezza — premesse inconsistenti,
binding mancanti, timeout/unknown NON diventano mai un via libera (il
fail-open per vacuita' che il passo 2 corregge).
CompatibilitySuite: dove la specifica non cambia, l'esito coincide con quello
del guard legacy (neurosymbolic_guard.SymbolicContract.evaluate).
"""

import z3

from cascade.guard_protocol import (
    GuardStatus,
    GuardVerdict,
    check_all,
    check_contract,
)
from cascade.neurosymbolic_guard import SymbolicContract, medical_guard


def _velocita_contract() -> SymbolicContract:
    v = z3.Int("velocita")
    lim = z3.Int("limite")
    return SymbolicContract(
        name="velocita<=limite",
        expressions=[z3.Not(v > lim)],
        symbols={"velocita": v, "limite": lim},
    )


def _unknown_solver(solver: z3.Solver) -> z3.CheckSatResult:
    return z3.unknown


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestCorrectnessSuite:
    # -- la tabella del documento (§7) --------------------------------------- #

    def test_coerente_che_rispetta_rules_verified(self):
        v = check_contract(_velocita_contract(), {"velocita": 30, "limite": 50})
        assert v.status is GuardStatus.RULES_VERIFIED
        assert v.proceed is True

    def test_coerente_che_viola_da_violazione_con_controesempio(self):
        v = check_contract(_velocita_contract(), {"velocita": 90, "limite": 50})
        assert v.status is GuardStatus.VIOLATION
        assert v.proceed is False
        assert v.counterexample is not None
        assert "velocita" in v.counterexample

    def test_premesse_contraddittorie_invalid_context_e_mai_permit(self):
        # velocita=30 AND velocita=90, limite=50: la "correzione" ingenua
        # (premesse ∧ ¬regole → unsat) APPROVAVA per vacuita'.
        v, w = z3.Int("velocita"), z3.Int("limite")
        premesse = (v == 30, v == 90)
        res = check_contract(
            _velocita_contract(), {"limite": 50}, premises=premesse)
        assert res.status is GuardStatus.INVALID_CONTEXT
        assert res.proceed is False
        assert res is not None

    # -- binding mancante / non tipizzabile: errore duro --------------------- #

    def test_missing_binding_is_a_hard_error(self):
        # 'limite' dichiarato ma non fornito: errore duRO, mai via libera
        v = check_contract(_velocita_contract(), {"velocita": 30})
        assert v.status is GuardStatus.MISSING_BINDING
        assert v.proceed is False

    def test_symbol_bound_only_via_premise_counts_as_provided(self):
        # velocita e' 'fornito' attraverso una premessa, limite via binding
        v, lim = z3.Int("velocita"), z3.Int("limite")
        res = check_contract(
            _velocita_contract(), {"limite": 50}, premises=(v == 30,))
        assert res.status is GuardStatus.RULES_VERIFIED

    def test_unsupported_binding_type_is_hard_error(self):
        v = check_contract(_velocita_contract(), {"velocita": 30, "limite": "cinquanta"})
        assert v.status is GuardStatus.MISSING_BINDING
        assert v.proceed is False

    # -- unknown/timeout: mai un via libera ---------------------------------- #

    def test_unknown_on_consistency_is_indeterminate(self):
        v, lim = z3.Int("velocita"), z3.Int("limite")
        res = check_contract(
            _velocita_contract(), {"limite": 50}, premises=(v == 30,),
            solver_check=_unknown_solver)
        assert res.status is GuardStatus.INDETERMINATE
        assert res.proceed is False

    def test_unknown_on_violation_search_is_indeterminate(self):
        class _UnknownOnce:
            def __init__(self):
                self.count = 0

            def __call__(self, solver):
                self.count += 1
                if self.count == 1:
                    return z3.sat            # premesse consistenti
                return z3.unknown            # ricerca violazione ignota

        res = check_contract(
            _velocita_contract(), {"velocita": 90, "limite": 50},
            solver_check=_UnknownOnce())
        assert res.status is GuardStatus.INDETERMINATE
        assert res.proceed is False

    def test_verdict_shape_guarantees(self):
        ok = GuardVerdict(GuardStatus.RULES_VERIFIED, "ok")
        assert ok.proceed is True
        for status in (GuardStatus.VIOLATION, GuardStatus.INVALID_CONTEXT,
                       GuardStatus.MISSING_BINDING, GuardStatus.INDETERMINATE):
            assert GuardVerdict(status, "x").proceed is False

    # -- aggregazione: qualunque esito duro salta tutto ---------------------- #

    def test_check_all_one_violation_poisons_all(self):
        guard = medical_guard()
        ok_ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
                  "allergia": False, "somministra": True}
        res = check_all(guard.contracts, ok_ctx)
        assert res.status is GuardStatus.RULES_VERIFIED

        bad_ctx = {"dosaggio": 600.0, "dosaggio_max": 500.0,
                   "allergia": False, "somministra": True}
        res = check_all(guard.contracts, bad_ctx)
        assert res.status is GuardStatus.VIOLATION
        assert res.proceed is False

    def test_check_all_missing_binding_beats_satisfied_contracts(self):
        guard = medical_guard()
        ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
               "allergia": False}                     # somministra manca
        res = check_all(guard.contracts, ctx)
        assert res.status is GuardStatus.MISSING_BINDING
        assert res.proceed is False

    def test_check_all_invalid_context_beats_everything(self):
        v = z3.Int("velocita")
        res = check_all(
            [_velocita_contract()], {"limite": 50}, premises=(v == 30, v == 90))
        assert res.status is GuardStatus.INVALID_CONTEXT


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #

_OK_MEDICAL = {"dosaggio": 400.0, "dosaggio_max": 500.0,
               "allergia": False, "somministra": True}


class TestCompatibilitySuite:
    def _legacy(self, contract, ctx):
        ok, cex = contract.evaluate(ctx)
        return ok, cex

    def test_same_verdict_as_legacy_on_good_context(self):
        guard = medical_guard()
        for contract in guard.contracts:
            legacy_ok, _ = self._legacy(contract, _OK_MEDICAL)
            v = check_contract(contract, _OK_MEDICAL)
            assert legacy_ok is True
            assert v.status is GuardStatus.RULES_VERIFIED

    def test_same_block_as_legacy_on_violation(self):
        # 600 > 500: il legacy ripiega/blocka, il protocollo da' VIOLATION
        dosaggio = z3.Real("dosaggio")
        dosaggio_max = z3.Real("dosaggio_max")
        contract = SymbolicContract(
            name="dosaggio_massimo",
            expressions=[z3.And(dosaggio > 0, dosaggio <= dosaggio_max)],
            symbols={"dosaggio": dosaggio, "dosaggio_max": dosaggio_max},
        )
        ctx = {"dosaggio": 600.0, "dosaggio_max": 500.0}
        legacy_ok, _ = self._legacy(contract, ctx)
        v = check_contract(contract, ctx)
        assert legacy_ok is False
        assert v.status is GuardStatus.VIOLATION

    def test_reuses_real_symbolic_contract_instances(self):
        # il protocollo lavora sugli stessi oggetti del guard esistente
        guard = medical_guard()
        ok = all(
            check_contract(c, _OK_MEDICAL).status is GuardStatus.RULES_VERIFIED
            for c in guard.contracts)
        assert ok

    def test_bindings_types_int_float_bool(self):
        guard = medical_guard()
        assert check_all(guard.contracts, dict(_OK_MEDICAL)).proceed is True

    def test_deterministic_between_runs(self):
        a = check_contract(_velocita_contract(), {"velocita": 30, "limite": 50})
        b = check_contract(_velocita_contract(), {"velocita": 30, "limite": 50})
        assert a == b and a.status is b.status

    def test_unknown_is_explicit_not_an_exception(self):
        # nei doc l'esito unknown non era gestito: ora e' un valore tipizzato
        res = check_contract(
            _velocita_contract(), {"velocita": 30, "limite": 50},
            solver_check=_unknown_solver)
        assert isinstance(res, GuardVerdict)
        assert res.status.value == "indeterminate"