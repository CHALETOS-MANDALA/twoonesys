"""Il claim nasce dal modello. Il kernel giudica. Mai float, mai auto-verifica."""

from cascade.claim_barrier import ClaimCode, canonical_payload_hash
from cascade.workers import WORKER_CALC, WORKER_PRISM, parse_model_claim_value, run_verified


def _rel(_q, _docs, top=1):
    return [(0, 0.9)]


def _evidence(kind, **kw):
    return {
        "intent": "zero_nth", "params": {"n": 1, "digits": 10},
        "immutable": True, "machine": {},
        "fact": {
            "kind": "zero_nth",
            "expected": [{"label": "Im", "value": "14.13472514", "float": 14.13}],
            "outcome": {"on_critical_line": True}, "payload": {},
        },
    }


BACKENDS = {WORKER_PRISM: _rel, WORKER_CALC: _evidence}


def test_senza_model_value_non_fabbrica_il_claim():
    rep = run_verified("quanto vale?", ["doc"], calc_args={"n": 1},
                       backends=BACKENDS)
    assert rep.verdict.ok is False
    assert rep.verdict.code is ClaimCode.MODEL_VALUE_MISSING
    assert rep.claim is None


def test_float_rifiutato_sul_percorso_verificato():
    rep = run_verified("x", ["doc"], calc_args={"n": 1},
                       backends=BACKENDS, model_value=14.1347)
    assert rep.verdict.ok is False
    assert rep.verdict.code is ClaimCode.FLOAT_FORBIDDEN


def test_claim_fedele_del_modello_passa():
    rep = run_verified("x", ["doc"], calc_args={"n": 1}, precision=4,
                       backends=BACKENDS, model_value="14.1347")
    assert rep.verdict.ok is True
    assert rep.claim is not None
    assert rep.claim.value == "14.1347"
    assert rep.claim.evidence_ref == canonical_payload_hash(_evidence("zeron"))


def test_claim_sbagliato_del_modello_fallisce():
    rep = run_verified("x", ["doc"], calc_args={"n": 1}, precision=4,
                       backends=BACKENDS, model_value="19.0000")
    assert rep.verdict.ok is False
    assert rep.verdict.code is ClaimCode.VALUE_DIGIT_MISMATCH


def test_parse_solo_claim_tipizzato_non_il_primo_numero():
    assert parse_model_claim_value("in 2 casi su 3 consiglio 2.5") is None
    assert parse_model_claim_value("CLAIM_VALUE=14.1347") == "14.1347"
    assert parse_model_claim_value('{"claim_value": "14.13"}') == "14.13"


def test_mutazione_kernel_come_claim_e_morta():
    """Se qualcuno rimette float(first['value']) questo test deve cadere:
    un model_value assente non puo' produrre verdict.ok."""
    rep = run_verified("x", ["doc"], calc_args={"n": 1}, precision=4,
                       backends=BACKENDS)
    assert not (rep.verdict.ok and rep.claim is not None)
