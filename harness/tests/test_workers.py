"""CASCADE - Passo 4: worker residenti (workers.py).

CorrectnessSuite: grafo di dipendenza, wiring della catena, nessun claim
fabbricato quando un backend manca. Smoke reali (PRISM e CalcKernel
in-process) dietro guardia di importabilita'.
CompatibilitySuite: l'evidenza prodotta in-process ha la SCHEMA identica a
matematica/evidenza e viene VERIFICATA dal barrier originale di matematica.
"""

import sys

import pytest

from cascade.claim_barrier import ClaimCode, canonical_payload_hash
from cascade.workers import (
    BackendUnavailable,
    ChainReport,
    WorkerStatus,
    WORKER_BARRIER,
    WORKER_CALC,
    WORKER_DOCS,
    WORKER_PRISM,
    calc_evidence,
    get_backend,
    prism_relevance,
    run_verified,
    upstream,
    validate_graph,
)

# --------------------------------------------------------------------------- #
# disponibilita' dei backend reali (sotto sforzo, come in produzione)
# --------------------------------------------------------------------------- #


def _calc_available() -> bool:
    try:
        calc_evidence("zeron", n=1, digits=10)
        return True
    except BackendUnavailable:
        return False


CALC_AVAILABLE = _calc_available()


def _prism_available() -> bool:
    """Un backend opzionale assente deve produrre uno SKIP, non un errore in
    raccolta: senza questa guardia l'intera suite non parte su una macchina
    che non ha PRISM importabile in-process."""
    if get_backend(WORKER_PRISM) is None:
        return False
    try:
        return bool(prism_relevance("batterie al sodio", ["batterie.", "musica."]))
    except BackendUnavailable:
        return False


PRISM_AVAILABLE = _prism_available()

# documento pertinente / fuori tema (stesso scenario delle misure di PRISM)
ON_TOPIC = ("Le batterie al sodio hanno densita' energetica Na-ion "
            "inferiore a Li-ion ma costo minore e sicurezza maggiore.")
OFF_TOPIC = ("Il dentifricio al fluoro protegge lo smalto ed e' indicato "
             "per la prevenzione della carie.")


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestGraph:
    def test_graph_is_a_known_dag(self):
        validate_graph()

    def test_prism_depends_on_retrieved_docs(self):
        assert upstream(WORKER_PRISM) == (WORKER_DOCS, WORKER_PRISM)

    def test_barrier_depends_on_calckernel(self):
        assert upstream(WORKER_BARRIER) == (WORKER_CALC, WORKER_BARRIER)

    def test_calckernel_has_no_upstream(self):
        assert upstream(WORKER_CALC) == (WORKER_CALC,)


class TestWiring:
    def test_hermetic_chain_with_injected_backends(self):
        def fake_rel(q, docs, top=1):
            return [(2, 0.91)]

        import json, hashlib

        def fake_evidence(kind, **kw):
            p = {"Im": "42.5000", "Re": "0.5", "on_critical_line": True}
            stdout = json.dumps(p)
            return {
                "intent": "zero_nth", "params": {"n": 42, "digits": 10},
                "immutable": True,
                "machine": {"tool": "mathkernel.calc", "args": ["zeron", 42],
                            "exit_code": 0,
                            "stdout_hash": hashlib.sha256(stdout.encode()).hexdigest()[:16],
                            "parsed": p},
                "fact": {
                    "kind": "zero_nth",
                    "expected": [{"label": "Im", "value": "42.5000", "float": 42.5},
                                 {"label": "Re", "value": "0.5", "float": 0.5,
                                  "boundary": True}],
                    "outcome": {"on_critical_line": True}, "payload": p,
                },
            }

        rep = run_verified(
            "quale zero?", ["a", "b", "zero 42"],
            calc_args={"n": 42, "digits": 10}, precision=4,
            model_value="42.5000",
            backends={WORKER_PRISM: fake_rel, WORKER_CALC: fake_evidence})

        assert rep.all_ok is True
        assert rep.verdict.ok is True
        assert rep.subject_id == "zero-42"
        assert rep.stages[-1].worker == WORKER_BARRIER
        assert rep.claim is not None and rep.claim.subject_id == "zero-42"

    def test_claim_ref_points_to_its_own_evidence(self):
        import json, hashlib

        def fake_rel(q, docs, top=1):
            return [(0, 0.7)]

        def fake_evidence(kind, **kw):
            return {"intent": "zero_nth", "params": {"n": 7, "digits": 10},
                    "immutable": True, "machine": {},
                    "fact": {"kind": "zero_nth",
                             "expected": [{"label": "Im", "value": "77.700",
                                           "float": 77.7}],
                             "outcome": {"on_critical_line": True},
                             "payload": {}}}

        rep = run_verified(
            "x", ["zero 7"], calc_args={"n": 7, "digits": 10}, precision=3,
            model_value="77.700",
            backends={WORKER_PRISM: fake_rel, WORKER_CALC: fake_evidence})
        assert rep.claim is not None
        assert rep.claim.evidence_ref == canonical_payload_hash(
            fake_evidence("zero_nth", n=7))
        assert rep.verdict.ok is True

    def test_backend_che_non_importa_non_fabbrica_claim(self):
        def _boom(*_a, **_k):
            raise BackendUnavailable("prism non importabile: simulato")

        rep = run_verified(
            "x", ["doc"], calc_args={"n": 1},
            backends={WORKER_PRISM: _boom})
        assert rep.verdict.ok is False
        assert rep.verdict.code is ClaimCode.NO_TOOL_EVIDENCE
        assert rep.stages[1].status is WorkerStatus.BLOCKED
        assert "simulato" in rep.stages[1].message

    def test_unknown_calc_kind_is_blocked_not_invented(self):
        def fake_rel(q, docs, top=1):
            return [(0, 0.5)]

        def fake_calc(kind, **kw):
            raise BackendUnavailable("calcolo sconosciuto: simulato")

        rep = run_verified(
            "x", ["doc"], calc_args={"n": 1},
            backends={WORKER_PRISM: fake_rel, WORKER_CALC: fake_calc})
        assert rep.all_ok is False
        assert any(s.status is WorkerStatus.BLOCKED for s in rep.stages)


@pytest.mark.skipif(not PRISM_AVAILABLE, reason="PRISM/numpy non disponibile")
class TestPrismResidente:
    def test_pertinente_vince_su_fuori_tema(self):
        scored = prism_relevance(
            "vantaggi delle batterie al sodio", [ON_TOPIC, OFF_TOPIC], top=2)
        assert scored[0][0] == 0               # il documento pertinente in testa
        assert scored[0][1] > scored[1][1]

    def test_calibrated_score_is_absolute(self):
        # il pavimento di rumore e' gia' tolto (PRISM calibrato)
        scored = prism_relevance("batterie al sodio", [OFF_TOPIC, OFF_TOPIC])
        assert scored[0][1] < 0.5

    def test_ranking_stable(self):
        docs = [ON_TOPIC, OFF_TOPIC, ON_TOPIC + " La sigla Na-ion aiuta."]
        a = prism_relevance("batterie al sodio", docs)
        b = prism_relevance("batterie al sodio", docs)
        assert [i for i, _ in a] == [i for i, _ in b]


@pytest.mark.skipif(not CALC_AVAILABLE, reason="mathkernel non importabile")
class TestCalcResidente:
    def test_zeron_evidence_numerica_inprocess(self):
        ev = calc_evidence("zeron", n=1, digits=20)
        im = ev["fact"]["expected"][0]["value"]
        assert im.startswith("14.13472514173469379")
        assert ev["machine"]["tool"] == "mathkernel.calc"

    def test_zeron_evidence_passa_la_barriera(self):
        from cascade.claim_barrier import NumericClaim, check_numeric_claim

        ev = calc_evidence("zeron", n=1, digits=20)
        claim = NumericClaim(
            operation="zeron", arguments=("1",), subject_id="zero-1",
            value=14.1347, unit="Im", precision=4,
            evidence_ref=canonical_payload_hash(ev))
        assert check_numeric_claim(claim, ev).ok is True

    @pytest.mark.skipif(not PRISM_AVAILABLE, reason="PRISM non disponibile")
    def test_chain_vertical_completa(self):
        ev = calc_evidence("zeron", n=1, digits=20)
        model_value = str(ev["fact"]["expected"][0]["value"])
        rep = run_verified(
            "l'Im del primo zero di zeta", [ON_TOPIC, OFF_TOPIC],
            calc_args={"n": 1, "digits": 20}, precision=5,
            model_value=model_value)
        assert rep.all_ok is True
        assert rep.verdict.ok is True
        assert rep.subject_id == "zero-1"


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #

_MATEMATICA_EVIDENZA = "C:\\Users\\andre\\Desktop\\matematica\\evidenza"

try:
    sys.path.append(_MATEMATICA_EVIDENZA)
    from barrier import verify as matematica_verify  # noqa: F401
    MATEMATICA_BARRIER = True
except Exception:  # noqa: BLE001
    MATEMATICA_BARRIER = False


def test_evidence_schema_identical_to_matematica():
    import json, hashlib

    p = {"Im": "14.5", "Re": "0.5", "on_critical_line": True}
    ev = {
        "intent": "zero_nth", "params": {"n": 1, "digits": 10},
        "immutable": True,
        "machine": {"tool": "mathkernel.calc", "args": ["zeron", 1, 10],
                    "exit_code": 0,
                    "stdout_hash": hashlib.sha256(json.dumps(p).encode()).hexdigest()[:16],
                    "parsed": p},
        "fact": {"kind": "zero_nth",
                 "expected": [{"label": "Im", "value": "14.5", "float": 14.5}],
                 "outcome": {"on_critical_line": True}, "payload": p},
    }
    assert set(ev) == {"intent", "params", "immutable", "machine", "fact"}
    assert set(ev["machine"]) == {"tool", "args", "exit_code",
                                  "stdout_hash", "parsed"}
    assert set(ev["fact"]) == {"kind", "expected", "outcome", "payload"}


@pytest.mark.skipif(not MATEMATICA_BARRIER or not CALC_AVAILABLE,
                    reason="barrier matematica non importabile")
def test_evidenza_inprocess_verificabile_da_matematica():
    # l'evidenza prodotta dal CalcKernel RESIDENTE in CASCADE e' consumata
    # dal barrier ORIGINALE di matematica: schema e cifre combaciano.
    ev = calc_evidence("zeron", n=1, digits=20)
    verdict = matematica_verify(ev, "l'Im e' 14.13472514173469")
    assert verdict.ok is True
    assert verdict.code == "EVIDENCE_OK"


@pytest.mark.skipif(not CALC_AVAILABLE, reason="mathkernel non importabile")
def test_inprocess_deterministico_tra_run():
    a = calc_evidence("zeron", n=1, digits=20)
    b = calc_evidence("zeron", n=1, digits=20)
    assert a == b
    assert canonical_payload_hash(a) == canonical_payload_hash(b)


def test_calc_unknown_kind_raises_not_fabricates():
    with pytest.raises(BackendUnavailable):
        calc_evidence("non-esiste")


def test_env_override_respected(monkeypatch):
    monkeypatch.setenv("CASCADE_MATEMATICA_KERNEL", "C:\\percorso\\inesistente")
    with pytest.raises(BackendUnavailable):
        calc_evidence("zeron", n=1, digits=6)


def test_backend_status_unregistered_is_blocked():
    assert get_backend(WORKER_DOCS) is None
    from cascade.workers import backend_status
    assert backend_status(WORKER_DOCS) is WorkerStatus.BLOCKED