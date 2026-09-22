"""CASCADE - Integrazione: barriera strutturata dei claim (claim_barrier).

CorrectnessSuite: gli invarianti della barriera - senza evidenza non c'e'
claim; il valore dichiarato deve essere un prefisso corretto delle cifre
dell'evidenza; l'oggetto si distingue per subject_id/ref, non per prosa.
CompatibilitySuite: il dialogo con l'evidenza di `matematica` e i tre hash
distinti del documento (LBP2 §11.1).
"""

from cascade.claim_barrier import (
    ClaimCode,
    ClaimRelation,
    DocumentClaim,
    NumericClaim,
    canonical_payload_hash,
    check_document_claim,
    check_numeric_claim,
    contains_declared_outcome,
    declarable_phrase,
    semantic_equivalence,
    transport_bytes_hash,
)

# cifre reali del kernel (math-kernel zetazero, 40 digits)
IM_Z1 = "14.13472514173469379045725198356247027078"
IM_Z50 = "143.1118458076206327394051238689139299662"


def _evidenza(im: str, n: int, stdout: str) -> dict:
    p = {"s": f"(0.5 + {im}j)", "Im": im, "Re": "0.5",
         "on_critical_line": True}
    run = {
        "tool": "math-kernel:zeron", "args": [str(n), "40"], "exit_code": 0,
        "stdout_hash": stdout, "parsed": p,
    }
    return {
        "intent": "zero_nth", "params": {"n": n, "digits": 40},
        "immutable": True, "machine": run,
        "fact": {
            "kind": "zero_nth",
            "expected": [
                {"label": "Im", "value": im, "float": float(im)},
                {"label": "Re", "value": "0.5", "float": 0.5, "boundary": True},
            ],
            "outcome": {"on_critical_line": True}, "payload": p,
        },
    }


EVIDENZA_Z1 = _evidenza(IM_Z1, 1, "a" * 16)
EVIDENZA_Z50 = _evidenza(IM_Z50, 50, "0" * 16)


def _claim_zero1(precision: int = 4, value: float = 14.1347) -> NumericClaim:
    return NumericClaim(
        operation="zeron", arguments=("1", "40"), subject_id="zero-1",
        value=value, unit="Im", precision=precision,
        evidence_ref=canonical_payload_hash(EVIDENZA_Z1))


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestCorrectnessSuite:
    def test_ok_truncated_value(self):
        v = check_numeric_claim(_claim_zero1(), EVIDENZA_Z1)
        assert v.ok is True
        assert v.code is ClaimCode.CLAIM_OK

    def test_ok_legacy_stdout_hash_ref(self):
        claim = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1347, unit="Im", precision=4,
            evidence_ref=EVIDENZA_Z1["machine"]["stdout_hash"])
        assert check_numeric_claim(claim, EVIDENZA_Z1).ok is True

    def test_altered_digit_rejected(self):
        v = check_numeric_claim(_claim_zero1(value=14.1348), EVIDENZA_Z1)
        assert v.ok is False
        assert v.code is ClaimCode.VALUE_DIGIT_MISMATCH

    def test_precision_beyond_evidence_rejected(self):
        v = check_numeric_claim(_claim_zero1(precision=50), EVIDENZA_Z1)
        assert v.ok is False
        assert v.code is ClaimCode.VALUE_DIGIT_MISMATCH

    def test_no_evidence_no_claim(self):
        assert check_numeric_claim(_claim_zero1(), None).code is \
            ClaimCode.NO_TOOL_EVIDENCE
        assert check_numeric_claim(_claim_zero1(), {}).code is \
            ClaimCode.NO_TOOL_EVIDENCE

    def test_subject_identity_is_the_ref_not_the_prose(self):
        # claim sul 50° zero c) ref dell'evidenza del 1° zero: respinto -
        # la barriera non mescola mai oggetti tra evidenze diverse.
        disc = NumericClaim(
            operation="zeron", arguments=("50", "40"), subject_id="zero-50",
            value=143.11184580762063, unit="Im", precision=10,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert check_numeric_claim(disc, EVIDENZA_Z1).ok is False

        # ref che non collega NESSUNA evidenza: rifiuto esplicito sul ref.
        ghost = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1347, unit="Im", precision=4,
            evidence_ref="0" * 16)
        v = check_numeric_claim(ghost, EVIDENZA_Z1)
        assert v.ok is False
        assert v.code is ClaimCode.EVIDENCE_REF_MISMATCH

        # stesso claim, con la SUA evidenza e le sue cifre: ok
        right = NumericClaim(
            operation="zeron", arguments=("50", "40"), subject_id="zero-50",
            value=143.11184580762063, unit="Im", precision=10,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z50))
        assert check_numeric_claim(right, EVIDENZA_Z50).ok is True

    def test_missing_subject_rejected(self):
        claim = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="",
            value=14.1347, unit="Im", precision=4,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert check_numeric_claim(claim, EVIDENZA_Z1).code is \
            ClaimCode.SUBJECT_MISSING

    def test_rounding_exact_short_evidence_ok(self):
        short = _evidenza("14.13", 1, "b" * 16)
        claim = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.13, unit="Im", precision=2, rounding_mode="exact",
            evidence_ref=canonical_payload_hash(short))
        assert check_numeric_claim(claim, short).ok is True

    def test_rounding_exact_tagliato_rejected(self):
        claim = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1347, unit="Im", precision=4, rounding_mode="exact",
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert check_numeric_claim(claim, EVIDENZA_Z1).ok is False

    # -- claim documentale (livello 2) -------------------------------------- #

    DOC = ("# Risultato\n"
           "Il 1° zero e' su Re=1/2. La cifra Im e' un dato di evidenza.\n"
           ).encode("utf-8")

    def test_document_claim_ok(self):
        claim = DocumentClaim(
            document_hash=transport_bytes_hash(self.DOC),
            document_version="v1", location="appunti.md:3",
            quoted_span="Il 1° zero e' su Re=1/2.",
            claim_relation=ClaimRelation.SUPPORTS)
        v = check_document_claim(claim, self.DOC)
        assert v.ok is True

    def test_document_hash_mismatch_rejected(self):
        claim = DocumentClaim(
            document_hash="0" * 64, document_version="v1",
            location="appunti.md:3", quoted_span="Il 1° zero e' su Re=1/2.",
            claim_relation=ClaimRelation.SUPPORTS)
        assert check_document_claim(claim, self.DOC).code is \
            ClaimCode.DOCUMENT_HASH_MISMATCH

    def test_quoted_span_missing_rejected(self):
        claim = DocumentClaim(
            document_hash=transport_bytes_hash(self.DOC),
            document_version="v1", location="appunti.md:3",
            quoted_span="lo zero viene PRIMA", claim_relation=ClaimRelation.MENTIONS)
        assert check_document_claim(claim, self.DOC).code is \
            ClaimCode.QUOTED_SPAN_MISSING

    # -- prosa dichiarativa (§8.1) ------------------------------------------ #

    def test_phrase_selected_by_value_not_by_prose(self):
        ok = _claim_zero1()
        refused = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1348, unit="Im", precision=4,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert "CLAIM_VERIFICATO" in declarable_phrase(ok, True)
        assert "CLAIM_RESPINTO" in declarable_phrase(refused, False)
        assert ok.subject_id in declarable_phrase(ok, True)
        assert ok.evidence_ref in declarable_phrase(ok, True)

    def test_free_prose_never_declares_outcome(self):
        assert contains_declared_outcome(
            "Il test e' riuscito: {{passed}}", True) is False
        assert contains_declared_outcome("CLAIM_VERIFICATO", True) is False


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #


class TestCompatibilitySuite:
    def test_truncation_tolerated_alteration_not(self):
        # stessa tolleranza del prefisso cifre di matematica
        assert check_numeric_claim(_claim_zero1(), EVIDENZA_Z1).ok is True
        assert check_numeric_claim(_claim_zero1(value=14.1348), EVIDENZA_Z1).ok \
            is False

    def test_three_hashes_are_distinct_operations(self):
        raw = b'{"a": 1}'
        t = transport_bytes_hash(raw)
        from json import loads
        c = canonical_payload_hash(loads(raw))
        assert t != c                     # byte di trasporto != forma canonica
        assert canonical_payload_hash({"a": 1, "b": 2}) == \
            canonical_payload_hash({"b": 2, "a": 1})   # ordine chiavi indifferente

    def test_semantic_equivalence_is_relative(self):
        assert semantic_equivalence("ZERO   uno", "zero uno") is True
        assert semantic_equivalence("14.1347", "14.1348") is False
        assert semantic_equivalence({"a": 1}, {"a": 1}) is True
        assert semantic_equivalence({"a": 1}, {"a": 2}) is False

    def test_canonical_ref_stable_across_runs(self):
        a = canonical_payload_hash(EVIDENZA_Z1)
        b = canonical_payload_hash(dict(EVIDENZA_Z1))
        assert a == b
        # questo stesso valore e' quello che ammette il claim
        assert _claim_zero1().evidence_ref == a

    def test_kwarg_order_and_equality(self):
        a = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1347, unit="Im", precision=4,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        b = NumericClaim(
            subject_id="zero-1", precision=4, value=14.1347,
            arguments=("1", "40"), unit="Im",
            operation="zeron", evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert (a, a) == (b, b) and hash(a) == hash(b)

    def test_unit_is_not_semantically_enforced(self):
        # la barriera verifica CIFRE e REF, non la dimensione; la semantics
        # dell'unita' resta un vincolo a valle (ma la unit... e' registrata)
        claim = NumericClaim(
            operation="zeron", arguments=("1", "40"), subject_id="zero-1",
            value=14.1347, unit="eV", precision=4,
            evidence_ref=canonical_payload_hash(EVIDENZA_Z1))
        assert check_numeric_claim(claim, EVIDENZA_Z1).ok is True

    def test_default_rounding_mode_is_truncation(self):
        assert _claim_zero1().rounding_mode == "truncation"