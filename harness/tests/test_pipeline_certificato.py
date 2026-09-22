"""CASCADE - Certificato: verdetto del solver e stato negli ingressi.

CorrectnessSuite. Richiede torch (importa `pipeline`). Cade sul codice
precedente, dove:

* `solver_status = "sat" if decision.approved else "blocked"` veniva dal FLAG
  di approvazione, non dal solver — un claim senza evidenza dentro l'artefatto
  che esiste per essere evidenza;
* `input_hash` leggeva `decision._state`, mai assegnato: lo stato non entrava
  nell'hash, e due decisioni prese da stati diversi avevano lo STESSO
  `input_hash`.
"""

import pytest

torch = pytest.importorskip("torch")

from cascade.a2a_protocol import AgentManifest, generate_keypair      # noqa: E402
from cascade.contracts import AgentSignal, Task                        # noqa: E402
from cascade.pipeline import CascadePipeline, PipelineConfig           # noqa: E402
from cascade.signing import KeyRegistry, SigningIdentity               # noqa: E402


def _pipe(tmp_path, **cfg) -> CascadePipeline:
    pipe = CascadePipeline(PipelineConfig(**cfg), key_store=tmp_path / "k.json")
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("a", pub, ["controllo"], 0.1, 0.9))
    return pipe


def _sig(action: float, confidence: float = 0.95) -> AgentSignal:
    return AgentSignal("a", {"action": action}, confidence=confidence,
                       capability="controllo")


class TestSolverStatusVieneDalSolver:
    def test_approvazione_dichiara_regole_verificate(self, tmp_path):
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        dec = pipe.run(Task("t1", "controllo", {}, max_cost=1.0),
                       [_sig(0.5, 0.7)], state=[0.5, 0.3])
        assert dec.approved
        assert dec.certificate.solver_status == "rules_verified"
        assert dec.certificate.solver_status != "sat"    # non e' piu' il flag

    def test_astensione_ood_dichiara_solver_non_interrogato(self, tmp_path):
        """Nel ramo OOD il guard NON viene mai chiamato: dirlo e' l'unica cosa
        onesta. Prima diceva 'blocked', come se il solver avesse deciso."""
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        dec = pipe.run(Task("t2", "controllo", {}, max_cost=1.0),
                       [_sig(0.5, 0.9)], state=[9.0, 8.0])
        assert dec.abstained
        assert dec.certificate.solver_status == "not_invoked"

    def test_lo_stato_di_solver_e_un_insieme_chiuso(self, tmp_path):
        ammessi = {"rules_verified", "violation", "not_invoked",
                   "invalid_context", "indeterminate"}
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        for stato, azione in (([0.5, 0.3], 0.5), ([9.0, 8.0], 0.5),
                              ([3.0, 2.0], 6.0)):
            dec = pipe.run(Task("t", "controllo", {}, max_cost=1.0),
                           [_sig(azione, 0.9)], state=stato)
            assert dec.certificate.solver_status in ammessi


class TestStatoNegliIngressi:
    def test_stati_diversi_danno_hash_diversi(self, tmp_path):
        """Il difetto in forma pura: stessa richiesta, stessa azione, stato
        diverso -> prima lo stesso input_hash."""
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        a = pipe.run(Task("h", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.5, 0.3])
        b = pipe.run(Task("h", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.1, 0.9])
        assert a.certificate.input_hash != b.certificate.input_hash

    def test_stesso_stato_stesso_hash(self, tmp_path):
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        a = pipe.run(Task("h", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.5, 0.3])
        b = pipe.run(Task("h", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.5, 0.3])
        assert a.certificate.input_hash == b.certificate.input_hash

    def test_il_rumore_entra_nell_hash(self, tmp_path):
        """`noise` cambia l'evidenza causale: deve cambiare anche l'hash."""
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        a = pipe.run(Task("n", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.5, 0.3], noise=False)
        b = pipe.run(Task("n", "controllo", {}, max_cost=1.0),
                     [_sig(0.5, 0.7)], state=[0.5, 0.3], noise=True)
        assert a.certificate.input_hash != b.certificate.input_hash


class TestFirmaDopoRiavvio:
    def test_certificato_verificabile_da_un_nuovo_processo(self, tmp_path):
        """Due pipeline distinte sullo stesso key store = il riavvio."""
        pipe = _pipe(tmp_path, confidence_threshold=0.5)
        dec = pipe.run(Task("f", "controllo", {}, max_cost=1.0),
                       [_sig(0.5, 0.7)], state=[0.5, 0.3])

        rinato = CascadePipeline(PipelineConfig(confidence_threshold=0.5),
                                 key_store=tmp_path / "k.json")
        assert rinato.identity.key_id == pipe.identity.key_id
        assert dec.certificate.verify_in(rinato.key_registry) is True
        assert dec.certificate.verify_signature(rinato._sign_pub) is True

    def test_identita_iniettabile(self, tmp_path):
        ident = SigningIdentity.generate()
        reg = KeyRegistry()
        pipe = CascadePipeline(PipelineConfig(confidence_threshold=0.5),
                               identity=ident, key_registry=reg)
        _, pub = generate_keypair()
        pipe.register_agent(AgentManifest("a", pub, ["controllo"], 0.1, 0.9))
        dec = pipe.run(Task("i", "controllo", {}, max_cost=1.0),
                       [_sig(0.5, 0.7)], state=[0.5, 0.3])
        assert dec.certificate.key_id == ident.key_id
        assert dec.certificate.verify_in(reg) is True
