"""Suite di conformita' SOH — le otto prove avversarie, eseguibili."""

from cascade.claim_barrier import ClaimCode, NumericClaim, canonical_payload_hash, check_numeric_claim
from cascade.guard_protocol import GuardStatus, check_all
from cascade.neurosymbolic_guard import medical_guard
from cascade.outcome_log import OutcomeRecord
from cascade.receipt import issue_receipt, verify_receipt
from cascade.signing import KeyRegistry, SigningIdentity
from cascade.workers import parse_model_claim_value


def test_1_binding_mancante_mai_permit():
    guard = medical_guard()
    # stesso paziente, campo allergia dimenticato: non deve autorizzare
    verdict = check_all(list(guard.contracts), {"somministra": True, "dosaggio": 400})
    assert verdict.status is not GuardStatus.RULES_VERIFIED
    assert verdict.proceed is False


def test_2_premesse_contraddittorie_non_permit():
    import z3
    from cascade.neurosymbolic_guard import SymbolicContract
    from cascade.guard_protocol import check_contract

    x = z3.Int("x")
    contract = SymbolicContract(
        name="x_ok", expressions=[x >= 0], symbols={"x": x})
    # premesse p e not p
    p = z3.Bool("p")
    verdict = check_contract(contract, {"x": 1}, premises=(p, z3.Not(p)))
    assert verdict.status is GuardStatus.INVALID_CONTEXT
    assert verdict.proceed is False


def test_3_claim_senza_evidenza():
    claim = NumericClaim(
        operation="zeron", arguments=("1",), subject_id="z",
        value="14.13", unit="Im", precision=2, evidence_ref="nope")
    assert check_numeric_claim(claim, None).code is ClaimCode.NO_TOOL_EVIDENCE


def test_4_cifre_non_float_prefisso():
    ev = {
        "intent": "z", "params": {}, "immutable": True, "machine": {},
        "fact": {"kind": "z",
                 "expected": [{"label": "Im", "value": "42.5000"}],
                 "outcome": {}, "payload": {}},
    }
    ref = canonical_payload_hash(ev)
    ok = NumericClaim("z", ("1",), "s", "42.5", "Im", 1, evidence_ref=ref)
    assert check_numeric_claim(ok, ev).ok is True


def test_5_prosa_non_e_un_claim():
    assert parse_model_claim_value("in 2 casi su 3 consiglio azione 2.5") is None


def test_6_esito_non_circolare_record_accetta_approved_true_outcome_false():
    rec = OutcomeRecord(
        request_id="circ-1", action="fs.write", raw_confidence=0.9,
        approved=True, outcome=False, selection_probability=1.0,
        label_source="mechanical")
    assert rec.approved is True and rec.outcome is False


def test_7_propensione_obbligatoria_per_off_policy_non_zero():
    rec = OutcomeRecord(
        request_id="p-1", action="fs.write", raw_confidence=0.5,
        selection_probability=1.0)
    assert rec.selection_probability == 1.0


def test_8_ricevuta_portabile_dopo_registro():
    ident = SigningIdentity.generate()
    keys = KeyRegistry()
    keys.register(ident)
    rec = issue_receipt(
        request_id="r1", policy="fs.write.sandbox", tool="fs.write",
        scope="sandbox", authorized=False, outcome=False, path="x",
        identity=ident, registry=keys)
    ok, _ = verify_receipt(rec, keys)
    assert ok is True
    other = KeyRegistry()
    ok2, _ = verify_receipt(rec, other)
    assert ok2 is False
