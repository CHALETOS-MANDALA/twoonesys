"""CASCADE - I quattro rischi aperti dell'audit, chiusi.

CorrectnessSuite. Ogni test cade sul codice precedente.

1. `eni_brain._extract_number` pescava l'azione di controllo dalla PROSA di un
   modello con una regex: *"in 2 casi su 3 consiglio azione 2.5"* -> 2.
2. `solver_status` del certificato veniva da `decision.approved`, non dal solver.
3. `input_hash` non includeva lo stato (`_state` non veniva mai assegnato).
4. La chiave di firma veniva rigenerata a ogni avvio: un certificato non era
   verificabile dopo un riavvio del processo.

I test 2 e 3 vivono in `test_pipeline_certificato.py` perche' richiedono torch;
qui stanno quelli che non lo richiedono.
"""

import asyncio

import pytest

from cascade.contracts import AgentSignal, DecisionCertificate
from cascade.eni_brain import ENIBrain, ProposalUnavailable, fake_eni_response
from cascade.signing import KeyRegistry, SigningIdentity

# --------------------------------------------------------------------------- #
# 1. l'azione non si deduce piu' dal testo
# --------------------------------------------------------------------------- #


async def _eni_solo_prosa(endpoint, payload, timeout):
    """ENI che risponde SOLO con prosa: nessun campo `action` tipizzato."""
    if endpoint == "/decision":
        return {"decision": {
            "confidence": 0.9,
            "best_branch": {"scenario": "riduzione", "posterior": 0.85},
            "rationale": "In 2 casi su 3 consiglio un'azione di controllo 2.5",
        }}
    return {"acceptance_probability": 80,
            "state_vector": {"confidence": 0.85, "risk": 0.2},
            "uncertainty": "bassa"}


class TestAzioneTipizzata:
    def test_prosa_senza_campo_tipizzato_non_produce_azione(self):
        """Il caso esatto del difetto: la regex avrebbe estratto 2 (da '2 casi
        su 3'). Ora, senza campo tipizzato e senza default, si rifiuta."""
        brain = ENIBrain(call_fn=_eni_solo_prosa)
        with pytest.raises(ProposalUnavailable):
            asyncio.run(brain.propose("controllo oscillatore"))

    def test_default_esplicito_e_dichiarato_come_tale(self):
        """Un default del chiamante e' ammesso, ma la provenienza va detta."""
        brain = ENIBrain(call_fn=_eni_solo_prosa)
        sig = asyncio.run(brain.propose("controllo", default_action=1.0))
        assert sig.proposal["action"] == 1.0
        assert sig.proposal["action_source"] == "caller_default"

    def test_campo_tipizzato_ha_la_precedenza(self):
        brain = ENIBrain(call_fn=fake_eni_response)
        sig = asyncio.run(brain.propose("controllo", default_action=99.0))
        assert sig.proposal["action"] == 2.5
        assert sig.proposal["action_source"] == "eni_typed"

    def test_la_confidenza_si_dichiara_non_calibrata(self):
        """Una media pesata di numeri auto-dichiarati non e' una probabilita':
        chi la riceve deve poterlo sapere dal dato, non dalla documentazione."""
        brain = ENIBrain(call_fn=fake_eni_response)
        sig = asyncio.run(brain.propose("controllo"))
        assert sig.proposal["confidence_kind"] == "raw_uncalibrated"

    def test_azione_non_numerica_non_passa(self):
        async def eni_rotto(endpoint, payload, timeout):
            if endpoint == "/decision":
                return {"decision": {"confidence": 0.9, "action": "circa 2.5",
                                     "best_branch": {}, "rationale": ""}}
            return {"acceptance_probability": 80, "state_vector": {}}
        brain = ENIBrain(call_fn=eni_rotto)
        with pytest.raises(ProposalUnavailable):
            asyncio.run(brain.propose("controllo"))

    def test_bool_non_e_un_azione(self):
        async def eni_bool(endpoint, payload, timeout):
            if endpoint == "/decision":
                return {"decision": {"confidence": 0.9, "action": True,
                                     "best_branch": {}, "rationale": ""}}
            return {"acceptance_probability": 80, "state_vector": {}}
        brain = ENIBrain(call_fn=eni_bool)
        with pytest.raises(ProposalUnavailable):
            asyncio.run(brain.propose("controllo"))

    def test_manifest_conserva_la_chiave_privata(self):
        """Prima: `_, pub = generate_keypair()` — la privata veniva buttata, e
        l'agente registrato non avrebbe mai potuto firmare un report."""
        from cascade.a2a_protocol import sign_bytes, verify_bytes
        brain = ENIBrain(call_fn=fake_eni_response)
        man = brain.manifest()
        firma = sign_bytes(brain._priv, b"report")
        assert verify_bytes(man.public_key, b"report", firma) is True

    def test_manifest_stabile_tra_chiamate(self):
        brain = ENIBrain(call_fn=fake_eni_response)
        assert brain.manifest().public_key == brain.manifest().public_key


# --------------------------------------------------------------------------- #
# 4. la firma sopravvive al riavvio e alla rotazione
# --------------------------------------------------------------------------- #


class TestIdentitaDiFirma:
    def test_identita_persiste_tra_due_processi(self, tmp_path):
        store = tmp_path / "k.json"
        a = SigningIdentity.load_or_create(store)
        b = SigningIdentity.load_or_create(store)      # il "riavvio"
        assert a.key_id == b.key_id
        assert a.public_bytes == b.public_bytes

    def test_certificato_verificabile_dopo_il_riavvio(self, tmp_path):
        store = tmp_path / "k.json"
        ident = SigningIdentity.load_or_create(store)
        reg = KeyRegistry(tmp_path / "known.json")
        reg.register(ident)

        cert = DecisionCertificate.create(
            decision_id="d1", input_obj={"a": 1}, policy_version="p1",
            model_versions={}, solver_status="rules_verified",
            proof_constraints=[], confidence=0.9, approved=True,
        ).sign_with(ident)

        # nuovo processo: ricarica identita' e storico da disco
        reg2 = KeyRegistry(tmp_path / "known.json")
        assert cert.verify_in(reg2) is True
        assert cert.key_id == ident.key_id

    def test_rotazione_non_invalida_i_certificati_vecchi(self, tmp_path):
        reg = KeyRegistry(tmp_path / "known.json")
        vecchia = SigningIdentity.generate()
        reg.register(vecchia)
        cert = DecisionCertificate.create(
            decision_id="d2", input_obj={}, policy_version="p1",
            model_versions={}, solver_status="rules_verified",
            proof_constraints=[], confidence=0.5, approved=True,
        ).sign_with(vecchia)

        nuova = SigningIdentity.generate()           # rotazione
        reg.register(nuova)
        assert cert.verify_in(reg) is True           # il passato resta verificabile
        assert len(reg) == 2

    def test_chiave_sconosciuta_non_e_valida_per_default(self, tmp_path):
        reg = KeyRegistry(tmp_path / "known.json")
        estranea = SigningIdentity.generate()        # MAI registrata
        cert = DecisionCertificate.create(
            decision_id="d3", input_obj={}, policy_version="p1",
            model_versions={}, solver_status="rules_verified",
            proof_constraints=[], confidence=0.5, approved=True,
        ).sign_with(estranea)
        assert cert.verify_in(reg) is False

    def test_manomissione_rilevata(self, tmp_path):
        reg = KeyRegistry(tmp_path / "known.json")
        ident = SigningIdentity.generate()
        reg.register(ident)
        cert = DecisionCertificate.create(
            decision_id="d4", input_obj={}, policy_version="p1",
            model_versions={}, solver_status="violation",
            proof_constraints=[], confidence=0.5, approved=False,
        ).sign_with(ident)
        assert cert.verify_in(reg) is True
        cert.solver_status = "rules_verified"        # bugia sul verdetto
        assert cert.verify_in(reg) is False

    def test_certificato_senza_key_id_non_si_verifica(self, tmp_path):
        reg = KeyRegistry(tmp_path / "known.json")
        ident = SigningIdentity.generate()
        reg.register(ident)
        cert = DecisionCertificate.create(
            decision_id="d5", input_obj={}, policy_version="p1",
            model_versions={}, solver_status="rules_verified",
            proof_constraints=[], confidence=0.5, approved=True,
        )
        cert.sign(ident.private_bytes)               # firma legacy, senza key_id
        assert cert.verify_in(reg) is False          # non si indovina la chiave
        assert cert.verify_signature(ident.public_bytes) is True   # compat

    def test_la_cartella_della_chiave_non_entra_in_git(self, tmp_path):
        store = tmp_path / "chiavi" / "k.json"
        SigningIdentity.load_or_create(store)
        assert (store.parent / ".gitignore").read_text(encoding="utf-8").strip() == "*"
