"""CASCADE - Integrazione: suite dei contratti System One v1.

Due suite, come da par. 13 di LBP2_CONTRATTI_V1:
* CorrectnessSuite — impone gli INVARIANTI, anche quando richiedono di
  cambiare l'output (qui: nessuna prova ne' probabilita' autorizza
  implicitamente).
* CompatibilitySuite — conserva il comportamento DOVE la specifica non cambia
  (valori, uguaglianza, hashing, digest deterministico).
"""

import math

import pytest

from cascade.contracts import sha256_hex
from cascade.contracts_v1 import (
    Assessment,
    Authorization,
    BackendCaps,
    CalibratedEstimate,
    CalibrationPolicy,
    CalibrationSupport,
    Deny,
    Estimated,
    EvidenceCoverage,
    ExecutionResult,
    Failed,
    Indeterminate,
    Insufficient,
    Permit,
    ProbabilityThreshold,
    Result,
    Review,
    Succeeded,
    UnwrapError,
    Verified,
    contract_digest,
)


def _est(value: float, digest: str, event: str = "ev_sufficient") -> CalibratedEstimate:
    return CalibratedEstimate(value=value, target_event=event, contract_digest=digest)


def _thr(value: float = 0.90, event: str = "ev_sufficient",
         action: str = "read") -> ProbabilityThreshold:
    return ProbabilityThreshold(value=value, target_event=event, action_class=action)


DIG_A = "digest-a"
DIG_B = "digest-b"


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE — gli invarianti che valgono ANCHE se cambiano l'output
# --------------------------------------------------------------------------- #


class TestCorrectnessSuite:
    # -- L'invariante centrale (par. 0-1): confini mai collassati ----------- #

    def test_verified_proof_is_never_an_authorization(self):
        prova = Verified(
            proposition="Re(rho_50)=1/2",
            value=True,
            evidence_ref="evidence/rh-50",
            assumptions=("rh-under-riemann",),
            verifier_ref="mathkernel:zetazero@0.1.0",
        )
        # una PROVA non e' un PERMESSO: tipi diversi, nessuna coercizione
        assert not isinstance(prova, Authorization)
        assert not isinstance(prova, Permit)
        assert not hasattr(prova, "grant_id")

    def test_high_probability_is_never_a_permit(self):
        stima = _est(0.98, DIG_A)
        assert isinstance(stima, CalibratedEstimate)
        assert not isinstance(stima, Permit)
        # la sola via di confronto e' la policy, e ritorna bool, mai un grant
        out = CalibrationPolicy("ev_sufficient", "read", {DIG_A}).accepts(
            stima, _thr(0.90))
        assert out is True
        assert isinstance(out, bool)

    def test_deny_wins_over_high_probability(self):
        # una probabilita' alta non supera un divieto: accettare la stima
        # NON produce un'autorizzazione; serve un Authorization esplicito
        deny = Deny(reason="policy: classe d'azione vietata")
        assert isinstance(deny, Deny)
        assert isinstance(deny, Authorization)
        # non esiste nessun percorso che trasformi l'esito della policy in un Permit
        assert "Permit" not in dir(CalibrationPolicy)

    def test_invariant_four_artifacts_are_distinct(self):
        # Assessment / Authorization / ExecutionResult: tre famiglie, nessun
        # membro appartiene a due famiglie
        samples_a: list[object] = [
            Verified("p", True, "r", (), "v"), _est(0.9, DIG_A), Insufficient("x")]
        samples_b: list[object] = [
            Permit("act", "arg", (), (), 0.0, "g1", "s1"), Deny("no"), Review("rv")]
        samples_c: list[object] = [
            Succeeded("rc", ("post",)), Failed("boom"), Indeterminate("rec")]
        for a in samples_a:
            assert not isinstance(a, Authorization)
            assert not isinstance(a, ExecutionResult)
        for b in samples_b:
            assert not isinstance(b, Assessment)
            assert not isinstance(b, ExecutionResult)
        for c in samples_c:
            assert not isinstance(c, Assessment)
            assert not isinstance(c, Authorization)

    # -- Tipi opachi (par. 12): CalibratedEstimate non e' un numero --------- #

    def test_estimate_rejects_out_of_range_and_non_finite(self):
        for bad in (1.5, -0.1, 2.0, math.nan, math.inf, -math.inf):
            with pytest.raises(ValueError):
                _est(bad, DIG_A)

    def test_estimate_has_no_comparison_nor_arithmetic(self):
        est = _est(0.90, DIG_A)
        thr = _thr(0.90)
        with pytest.raises(TypeError):
            est > thr                # niente __gt__: confronto grezzo vietato
        with pytest.raises(TypeError):
            est + 1.0                # niente __add__
        with pytest.raises(TypeError):
            float(est)               # niente __float__: non e' un numero

    def test_estimate_requires_digest(self):
        with pytest.raises(ValueError):
            CalibratedEstimate(value=0.9, target_event="e", contract_digest="")

    # -- Policy: il contesto e' verificato, mai presupposto ----------------- #

    def test_policy_checks_target_event_and_action_class(self):
        policy = CalibrationPolicy("ev_sufficient", "read", {DIG_A})
        assert policy.accepts(_est(0.95, DIG_A), _thr(0.90, event="ev_sufficient")) is True
        assert policy.accepts(_est(0.95, DIG_A), _thr(0.90, event="ev_OTHER")) is False
        assert policy.accepts(_est(0.95, DIG_A), _thr(0.90, action="write")) is False

    def test_non_applicable_digest_never_accepts(self, ):
        policy = CalibrationPolicy("ev_sufficient", "read", {DIG_A})
        # stima prodotta da un calibratore NON registrato: non applicabile
        assert policy.applicable(_est(0.95, DIG_B)) is False
        assert policy.accepts(_est(0.95, DIG_B), _thr(0.90)) is False
        # digest aperti (registro vuoto) = nessuna restrizione sul fronte digest
        open_policy = CalibrationPolicy("ev_sufficient", "read", frozenset())
        assert open_policy.applicable(_est(0.95, DIG_B)) is True

    def test_threshold_below_value_only_accepts_when_records_match(self):
        policy = CalibrationPolicy("ev_sufficient", "read", {DIG_A, DIG_B})
        assert policy.accepts(_est(0.80, DIG_A), _thr(0.70)) is True
        assert policy.accepts(_est(0.80, DIG_A), _thr(0.90)) is False
        assert policy.accepts(_est(0.95, DIG_B), _thr(0.70)) is True  # entrambi registrati

    # -- Indeterminate: un timeout non e' un fallimento ---------------------- #

    def test_indeterminate_is_not_a_failure(self):
        esito = Indeterminate(reconciliation_ref="run/42")
        assert isinstance(esito, ExecutionResult)
        assert not isinstance(esito, Failed)
        assert esito.reconciliation_ref == "run/42"
        # l'errore di un vero fallimento resta Failed
        assert isinstance(Failed("err"), Failed)

    # -- contract_digest: qualunque cambiamento invalida --------------------- #

    def test_digest_changes_with_any_component(self):
        assert contract_digest(schema=1, stage="cal") != contract_digest(schema=2, stage="cal")
        assert contract_digest(scorer="prism-v1", features=["a"]) != \
            contract_digest(scorer="prism-v1", features=["a", "b"])
        assert contract_digest(label="proto") != contract_digest(label="protox")

    # -- Result: l'errore tipizzato rende possibile il parziale -------------- #

    def test_taskgroup_failure_keeps_partial_results(self):
        # due produttori, uno fallisce: la task fallita 'e' un VALORE, non
        # un'eccezione che cancella le altre (par. 11)
        esiti = [Result.ok(41), Result.err("timeout:produttore-2")]
        parziali = [r.unwrap() for r in esiti if r.is_ok]
        errori = [r.error for r in esiti if r.is_err]
        assert parziali == [41]
        assert errori == ["timeout:produttore-2"]
        with pytest.raises(UnwrapError):
            esiti[1].unwrap()       # assert di programmazione, non flusso atteso

    def test_indeterminate_state_maps_to_reconciliation_not_error(self):
        # il timeout registra uno stato ignoto, non un errore archiviato
        esiti: list[Result] = []
        esiti.append(Result.ok(Succeeded("rc")))
        esiti.append(Result.err(Indeterminate("reconciliation/run-42")))
        assert isinstance(esiti[1].error, Indeterminate)

    # -- BackendCaps: alla cieca si assume il NON-supporto ------------------- #

    def test_backend_caps_fail_closed_defaults(self):
        caps = BackendCaps(name="anonimo")
        assert caps.logprobs is False and caps.grammar is False
        assert caps.max_cardinality == 1
        with pytest.raises(ValueError):
            BackendCaps(name="x", max_cardinality=0)

    def test_backend_caps_frozen(self):
        caps = BackendCaps(name="x", logprobs=True)
        with pytest.raises(Exception):
            caps.logprobs = False    # type: ignore[misc]


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE — comportamento conservato dove la specifica non cambia
# --------------------------------------------------------------------------- #


class TestCompatibilitySuite:
    def _prova(self) -> Verified:
        return Verified("p", True, "r", ("ass",), "v")

    # -- Result -------------------------------------------------------------- #

    def test_result_ok_preserves_value_identity(self):
        obj = {"id": 7}
        r = Result.ok(obj)
        assert r.is_ok and not r.is_err
        assert r.unwrap() is obj
        assert r.unwrap_or({}) is obj

    def test_result_err_preserves_error(self):
        e = KeyError("k")
        r = Result.err(e)
        assert r.is_err and not r.is_ok
        assert r.error is e
        assert r.unwrap_or("fallback") == "fallback"

    def test_result_eq_and_hash(self):
        assert Result.ok(3) == Result.ok(3)
        assert Result.err("a") == Result.err("a")
        assert Result.ok(3) != Result.err(3)
        assert hash(Result.ok(3)) == hash(Result.ok(3))

    def test_result_map_preserves_err(self):
        r = Result.ok(2).map(lambda x: x * 10)
        assert r == Result.ok(20)
        assert Result.err("e").map(lambda x: x * 10) == Result.err("e")

    # -- Dataclass frozen e hashable ----------------------------------------- #

    def test_assessment_family_unchanged_by_construction(self):
        assert self._prova().proposition == "p"
        assert self._prova().assumptions == ("ass",)
        assert hash(self._prova()) == hash(Verified("p", True, "r", ("ass",), "v"))
        assert self._prova() == Verified("p", True, "r", ("ass",), "v")

    def test_authorization_family_frozen_hashable(self):
        p = Permit("act", "arg", ("s",), ("pre",), 1.0, "g-1", "sub-1")
        assert p.grant_id == "g-1" and p.subject_id == "sub-1"
        assert hash(p) == hash(Permit("act", "arg", ("s",), ("pre",), 1.0, "g-1", "sub-1"))
        assert Deny("no") != Review("no")      # stessa stringa, ruoli diversi

    def test_execution_family_frozen_hashable(self):
        s = Succeeded("rc", ("post",))
        assert s.receipt == "rc" and s.observed_postconditions == ("post",)
        assert s == Succeeded("rc", ("post",))
        assert Indeterminate("r") == Indeterminate("r")

    # -- CalibratedEstimate: valore leggibile, mai aritmetica ---------------- #

    def test_estimate_value_readable_and_bound_to_event(self):
        est = _est(0.9201, DIG_A, event="ev_sufficient")
        assert est.value == 0.9201
        assert est.target_event == "ev_sufficient"
        assert est.contract_digest == DIG_A
        assert est == _est(0.9201, DIG_A, event="ev_sufficient")

    def test_estimate_boundaries_stable(self):
        assert _est(0.0, DIG_A).value == 0.0
        assert _est(1.0, DIG_A).value == 1.0

    # -- SupportStatus / Coverage / CalibrationSupport (par. 6) -------------- #

    def test_support_datatypes_stable(self):
        from cascade.contracts_v1 import SupportStatus
        assert SupportStatus.SUPPORTED.value == "supported"
        assert EvidenceCoverage("missing_requirements").state == "missing_requirements"
        assert CalibrationSupport(100, "eval/1", "valid").sample_count == 100
        assert EvidenceCoverage("x") == EvidenceCoverage("x")

    # -- contract_digest: deterministico e indipendente dall'ordine ---------- #

    def test_digest_deterministic_and_order_independent(self):
        d1 = contract_digest(schema=1, stage="cal", scorer="prism-v1")
        d2 = contract_digest(stage="cal", scorer="prism-v1", schema=1)
        assert d1 == d2
        assert d1 == sha256_hex(
            {"schema": 1, "stage": "cal", "scorer": "prism-v1"})
        # valorizzato allo stesso modo = stesso digest, anche con nidificazione
        assert contract_digest(extra={"a": [1, 2]}) == contract_digest(extra={"a": [1, 2]})

    def test_digest_alphanumeric(self):
        assert contract_digest(a=1).isalnum()

    # -- shape guard della migrazione: i campi del Permit ci sono ------------- #

    def test_permit_shape_guards_future_changes(self):
        p = Permit("act", "arg", (), (), 0.0, "g", "s")
        for field in ("action_digest", "arguments_digest", "scope", "preconditions",
                      "expires_at", "grant_id", "subject_id"):
            assert hasattr(p, field), f"Permit ha perso il campo {field}"
        # anti-riuso e scadenza sono parte del contratto dalla prima riga
        assert p.grant_id and p.expires_at == 0.0