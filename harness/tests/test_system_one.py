"""CASCADE - Passo 7: il circuito chiuso del System One (system_one.py).

CorrectnessSuite: il gate usa la probabilita' MISURATA (mai quella
auto-dichiarata), ECE calibrato < ECE grezzo, cold start senza storia = mai
via libera, Indeterminate non alimenta il misuratore, TOCTOU bloccato,
grant monouso.
CompatibilitySuite: restart dalla log (curva identica), cablaggio con
ReliabilityMeter+ConformalCalibrator, verifica del verificatore con margine
sui contratti Z3 reali.
"""

import time

import numpy as np
import z3

from cascade.action_authorize import GrantRegistry, grant_from_permit
from cascade.contracts_v1 import (
    Permit,
    Succeeded,
    contract_digest,
)
from cascade.escalation import EscalationReason
from cascade.guard_protocol import GuardStatus
from cascade.neurosymbolic_guard import SymbolicContract as SC
from cascade.outcome_log import OutcomeLog, OutcomeRecord
from cascade.reliability import ReliabilityMeter
from cascade.system_one import SystemOneLoop


# --------------------------------------------------------------------------- #
# mappe agente->esito (reproducibili)
# --------------------------------------------------------------------------- #


def _biased_meter(seed: int = 7, n: int = 400) -> ReliabilityMeter:
    """Agente OVERCONFIAdENTE: dichiara fino a 1.0 ma il mondo da' <= 0.80."""
    rng = np.random.default_rng(seed)
    meter = ReliabilityMeter()
    confs = rng.uniform(0.5, 1.0, n)
    outs = rng.random(n) < np.minimum(confs, 0.80)
    return meter.record_many(confs.tolist(), outs.tolist()).fit()


def _honest_meter(seed: int = 3, n: int = 400) -> ReliabilityMeter:
    """Agente ben calibrato: P(successo) = confidenza dichiarata."""
    rng = np.random.default_rng(seed)
    meter = ReliabilityMeter()
    confs = rng.uniform(0.5, 1.0, n)
    outs = rng.random(n) < confs
    return meter.record_many(confs.tolist(), outs.tolist()).fit()


def _grant_pair(request_id: str, params: dict):
    permit = Permit(
        action_digest=contract_digest(action="file_write", scope="fs.write"),
        arguments_digest=contract_digest(**params),
        scope=("fs.write",), preconditions=(), expires_at=time.time() + 3600,
        grant_id=request_id, subject_id="zero-1")
    grant = grant_from_permit(
        permit, tool="file_write", scope="fs.write", params=params,
        request_id=request_id, operation_id=request_id)
    reg = GrantRegistry()
    reg.issue(grant)
    return reg, permit, grant


def _executor(calls: list):
    return lambda p: calls.append(p) or {"ok": True}


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestGateCalibrato:
    def test_cold_start_mai_via_libera(self):
        loop = SystemOneLoop()
        a = loop.assess("r1", "file_write", 0.9)
        assert a.readout.measured_p is None        # nessuna misura: niente finto
        assert a.estimate is None
        assert a.escalate is True
        assert a.reason is EscalationReason.HIGH_RISK

    def test_cold_start_senza_system_two_indeterminate(self):
        loop = SystemOneLoop()
        a = loop.assess("r1", "file_write", 0.9)
        res, done = loop.dispose(a)
        assert isinstance(res, Succeeded) is False
        assert "system_two" in getattr(res, "reconciliation_ref", "")
        assert done is False

    def test_cold_start_system_two_che_blocca_non_esegue(self):
        loop = SystemOneLoop()
        a = loop.assess("r1", "file_write", 0.9)
        calls: list = []
        res, done = loop.dispose(a, system_two=lambda: False, executor=_executor(calls))
        assert "non_approva" in getattr(res, "error", "")
        assert calls == []

    def test_agente_overconfidente_viene_degradato(self):
        loop = SystemOneLoop(meter=_biased_meter())
        a = loop.assess("r1", "file_write", 0.95)
        assert a.estimate is not None
        assert 0.7 < a.estimate.value < 0.9         # 0.95 dichiarata -> ~0.80 misurata
        assert a.escalate is True                   # la misura NON passa il gate

    def test_agente_onesto_viene_accettato(self):
        loop = SystemOneLoop(meter=_honest_meter())
        a = loop.assess("r1", "file_write", 0.95)
        assert a.readout.measured_p is not None
        assert a.readout.measured_p >= 0.90
        assert a.escalate is False
        assert a.reason is EscalationReason.NO_SIGNAL

    def test_ece_calibrato_minore_del_grezzo(self):
        meter = _biased_meter()
        ece_raw = meter.ece(calibrated=False)
        ece_cal = meter.ece(calibrated=True)
        assert ece_cal < ece_raw
        assert ece_cal < 0.05

    def test_determinismo_su_stessa_storia(self):
        m1, m2 = _biased_meter(7), _biased_meter(7)
        a1 = SystemOneLoop(meter=m1).assess("x", "a", 0.90)
        a2 = SystemOneLoop(meter=m2).assess("x", "a", 0.90)
        assert a1.readout.measured_p == a2.readout.measured_p


class TestCircuitoChiuso:
    def test_giro_completo_esegue_e_registra(self, tmp_path):
        log = OutcomeLog(tmp_path / "out.jsonl")
        meter = _honest_meter()
        before = meter.size
        loop = SystemOneLoop(meter=meter, log=log)
        calls: list = []
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        out = loop.process(
            request_id="r1", action="file_write", raw_confidence=0.95,
            permit=permit, grant_doc=grant.to_dict(), registry=reg,
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "a"}, executor=_executor(calls))
        a, res = out
        assert isinstance(res, Succeeded)
        assert calls == [{"path": "a"}]
        assert log.size == 1
        rec = log.records()[0]
        assert rec.approved is True and rec.outcome is True
        assert rec.raw_confidence == 0.95
        # il metro si e' aggiornato con l'esito reale
        assert loop.meter.size == before + 1

    def test_grant_monouso(self):
        loop = SystemOneLoop(meter=_honest_meter(), log=OutcomeLog())
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        loop.process(
            request_id="r1", action="file_write", raw_confidence=0.95,
            permit=permit, grant_doc=grant.to_dict(), registry=reg,
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "a"}, executor=_executor([]))
        replay = reg.authorize(grant.to_dict(), tool="file_write",
                               scope="fs.write", params={"path": "a"})
        assert replay.is_err and "grant_used" in replay.error

    def test_toctou_bloccato_prima_dell_esecutore(self):
        loop = SystemOneLoop(meter=_honest_meter(), log=OutcomeLog())
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        calls: list = []
        a, res = loop.process(
            request_id="r1", action="file_write", raw_confidence=0.95,
            permit=permit, grant_doc=grant.to_dict(), registry=reg,
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "b"}, executor=_executor(calls))   # stato cambiato
        assert "TOCTOU" in getattr(res, "error", "")
        assert calls == []

    def test_indeterminate_non_alimenta_il_metro(self, tmp_path):
        loop = SystemOneLoop(meter=_honest_meter(),
                             log=OutcomeLog(tmp_path / "out.jsonl"))
        before = loop.meter.size
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        a, res = loop.process(
            request_id="r1", action="file_write", raw_confidence=0.95,
            permit=permit, grant_doc=grant.to_dict(), registry=reg,
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "a"}, executor=None)              # risposta persa
        assert hasattr(res, "reconciliation_ref")
        rec = loop.log.records()[0]
        assert rec.outcome is None                           # ignoto: non e' un esito
        assert loop.meter.size == before                    # il metro NON cresce
        assert loop.log.metrics()["settled"] == 0

    def test_settle_con_esito_esplicito(self):
        meter = _honest_meter()
        before = meter.size
        loop = SystemOneLoop(meter=meter, log=OutcomeLog())
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        a = loop.assess("r1", "file_write", 0.95)
        res, _ = loop.dispose(a, registry=reg, permit=permit,
                              grant_doc=grant.to_dict(), tool="file_write",
                              scope="fs.write", params={"path": "a"},
                              state={"path": "a"}, executor=_executor([]))
        loop.settle(a, res, outcome=False)                  # il mondo dice no
        assert loop.meter.size == before + 1

    def test_approved_e_outcome_separati_nel_record(self):
        """B2: il RECORD deve poter contenere approved != outcome.

        `approved` = il gate ha eseguito con Succeeded; `outcome` arriva da una
        lettura del mondo (qui esplicita). Il record li tiene SEPARATI: un
        outcome osservato non e' mai derivato dall'approvazione.
        """
        loop = SystemOneLoop(meter=_honest_meter(), log=OutcomeLog())
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        a = loop.assess("r1", "file_write", 0.95)
        res, _ = loop.dispose(a, registry=reg, permit=permit,
                              grant_doc=grant.to_dict(), tool="file_write",
                              scope="fs.write", params={"path": "a"},
                              state={"path": "a"}, executor=_executor([]))
        assert isinstance(res, Succeeded)                    # il gate ha eseguito
        loop.settle(a, res, outcome=False)                   # ...ma il mondo dice no
        rec = loop.log.records()[0]
        assert rec.approved is True
        assert rec.outcome is False
        assert rec.approved != rec.outcome                   # mai collassati

    def test_action_chosen_viaggia_fino_al_record(self):
        """B3: l'identita' del braccio scelto arriva fino alla log, per IPS/dr."""
        loop = SystemOneLoop(meter=_honest_meter(), log=OutcomeLog())
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        a, res = loop.process(
            request_id="r1", action="file_write", raw_confidence=0.95,
            permit=permit, grant_doc=grant.to_dict(), registry=reg,
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "a"}, executor=_executor([]),
            action_chosen="scrittura_autorizzata")
        assert isinstance(res, Succeeded)
        rec = loop.log.records()[0]
        assert rec.action_chosen == "scrittura_autorizzata"
        # round-trip: sopravvive alla serializzazione
        assert OutcomeRecord.from_json(rec.to_json()).action_chosen == rec.action_chosen


class TestEscalationInOmbraChiusa:
    def test_escalation_settled_e_report(self, tmp_path):
        log = OutcomeLog(tmp_path / "out.jsonl")
        # agente overconfidente -> la misura lo scala a System 2
        loop = SystemOneLoop(meter=_biased_meter(), log=log)
        reg, permit, grant = _grant_pair("r1", {"path": "a"})
        a = loop.assess("r1", "file_write", 0.95)
        assert a.escalate is True
        res, done = loop.dispose(a, system_two=lambda: True, registry=reg,
                                 permit=permit, grant_doc=grant.to_dict(),
                                 tool="file_write", scope="fs.write",
                                 params={"path": "a"}, state={"path": "a"},
                                 executor=_executor([]))
        loop.settle(a, res)
        rep = loop.shadow.report()
        assert rep["settled"] == 1
        assert rep["escalated"] == 1
        assert rep["system_two_catches"] is not None
        assert rep["system_two_catches"] == 0.0     # S2 ha APPOGGIATO


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #


class TestRestartECompatibilita:
    def test_restart_ricostruisce_curva_identica(self, tmp_path):
        p = tmp_path / "out.jsonl"
        a = SystemOneLoop(meter=_honest_meter(), log=OutcomeLog(p))
        for i in range(120):
            rid = f"r{i}"
            reg, permit, grant = _grant_pair(rid, {"path": rid})
            a.process(request_id=rid, action="file_write",
                      raw_confidence=0.6 + (i % 40) / 100.0,
                      permit=permit, grant_doc=grant.to_dict(), registry=reg,
                      tool="file_write", scope="fs.write", params={"path": rid},
                      state={"path": rid}, executor=(lambda p_: {"ok": True}),
                      system_two=lambda: True)     # escalazioni appoggiate da S2
        assert a.log.size == 120
        assert a.log.metrics()["settled"] == 120   # 120 esiti NOTI su disco
        # restart: lo stato e' SOLO dal registro, identico a ogni giro
        b1, b2 = SystemOneLoop.from_log(p), SystemOneLoop.from_log(p)
        assert b1.meter.size == b2.meter.size == 120
        for c in (0.55, 0.7, 0.85, 0.95):
            assert abs(b1.meter.calibrate(c) - b2.meter.calibrate(c)) < 1e-12

    def test_conformal_risk_cablaggio(self):
        conformal = type("Fake", (), {"__getattr__": lambda s, n: None})()
        loop = SystemOneLoop(meter=_honest_meter(), conformal=conformal)
        a = loop.assess("r1", "file_write", 0.5, conformal_risk=0.35)
        assert abs(a.risk - 0.35) < 1e-12


class TestVerificaDelVerificatore:
    def _velocita(self):
        v, lim = z3.Int("velocita"), z3.Int("limite")
        return SC(name="velocita<=limite",
                  expressions=[z3.Not(v > lim)],
                  symbols={"velocita": v, "limite": lim})

    def test_witness_margine_certifica_il_via_libera(self):
        c = self._velocita()
        loop = SystemOneLoop()
        verdict, witness = loop.guard_check([c], {"velocita": 30, "limite": 50})
        assert verdict.status is GuardStatus.RULES_VERIFIED
        assert witness.ok is True
        assert abs(witness.margin - 20.0) < 1e-9        # 50 - 30

    def test_margine_piccolo_al_confine(self):
        c = self._velocita()
        _, w_near = SystemOneLoop().guard_check(
            [c], {"velocita": 49, "limite": 50})
        _, w_far = SystemOneLoop().guard_check(
            [c], {"velocita": 10, "limite": 50})
        assert abs(w_near.margin - 1.0) < 1e-9
        assert abs(w_far.margin - 40.0) < 1e-9
        assert w_near.margin < w_far.margin

    def test_violazione_mai_certificata(self):
        c = self._velocita()
        verdict, witness = SystemOneLoop().guard_check(
            [c], {"velocita": 90, "limite": 50})
        assert verdict.status is GuardStatus.VIOLATION
        assert witness.ok is False

    def test_premesse_contraddittorie_nessun_modello(self):
        v = z3.Int("velocita")
        c = self._velocita()
        verdict, witness = SystemOneLoop().guard_check(
            [c], {"limite": 50}, premises=(v == 30, v == 90))
        assert verdict.status is GuardStatus.INVALID_CONTEXT
        assert witness.ok is False                       # nessun mondo testimone

    def test_regole_booleane_senza_margine_numerico(self):
        allergy = z3.Bool("allergia")
        admit = z3.Bool("somministra")
        c_no_allergia = SC(name="no_allergia",
                           expressions=[z3.Not(z3.And(allergy, admit))],
                           symbols={"allergia": allergy, "somministra": admit})
        dose, dose_max = z3.Real("dosaggio"), z3.Real("dosaggio_max")
        c_dose = SC(name="dose_sicura",
                    expressions=[z3.And(dose > 0, dose <= dose_max)],
                    symbols={"dosaggio": dose, "dosaggio_max": dose_max})
        verdict, witness = SystemOneLoop().guard_check(
            [c_no_allergia, c_dose],
            {"allergia": False, "somministra": True,
             "dosaggio": 400.0, "dosaggio_max": 600.0})
        assert verdict.status is GuardStatus.RULES_VERIFIED
        assert witness.ok is True
        assert abs(witness.margin - 200.0) < 1e-9        # min(400, 200)
        # solo la regola booleana: margine None, non 0
        _, w_bool = SystemOneLoop().guard_check(
            [c_no_allergia], {"allergia": False, "somministra": True})
        assert w_bool.ok is True and w_bool.margin is None

    def test_witness_deterministico(self):
        c = self._velocita()
        _, w1 = SystemOneLoop().guard_check([c], {"velocita": 30, "limite": 50})
        _, w2 = SystemOneLoop().guard_check([c], {"velocita": 30, "limite": 50})
        assert w1.margin == w2.margin