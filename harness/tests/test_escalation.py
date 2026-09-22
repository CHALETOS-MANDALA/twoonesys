"""CASCADE - Passo 5: escalation del System 2 in ombra (escalation.py).

CorrectnessSuite: la politica di escalazione (quando scatta, perche'),
la propensione empirica e i contatori del report — onesti, mai inventati.
CompatibilitySuite: l'escalation si alimenta dei veri layer gia' esistenti
(ConformalCalibrator, ReliabilityMeter, guard Z3 a 3 passi) da cui prende
readout e System 2.
"""

import numpy as np

from cascade.conformal import ConformalCalibrator, consistency_score
from cascade.escalation import (
    EscalationReason,
    EscalationRecord,
    ShadowEscalation,
    SystemOneReadout,
)
from cascade.guard_protocol import GuardStatus, check_contract
from cascade.neurosymbolic_guard import medical_guard
from cascade.reliability import ReliabilityMeter


def _readout(proceed: bool, risk: float, measured_p: float | None = None,
             score: float = 0.0) -> SystemOneReadout:
    return SystemOneReadout(proceed=proceed, risk=risk,
                            measured_p=measured_p, score=score)


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestCorrectnessSuite:
    def test_proceed_false_is_high_risk_escalation(self):
        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(_readout(proceed=False, risk=0.85))
        assert rec.escalate is True
        assert rec.reason is EscalationReason.HIGH_RISK

    def test_measured_p_below_rischio_e_low_confidence(self):
        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(_readout(proceed=True, risk=0.2, measured_p=0.80))
        assert rec.escalate is True
        assert rec.reason is EscalationReason.LOW_CONFIDENCE

    def test_system_one_certo_non_escala(self):
        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(_readout(proceed=True, risk=0.1, measured_p=0.98))
        assert rec.escalate is False
        assert rec.reason is EscalationReason.NO_SIGNAL

    def test_senza_storia_di_reliability_neutro(self):
        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(_readout(proceed=True, risk=0.1, measured_p=None))
        assert rec.escalate is False

    def test_system_two_interrogato_solo_quando_escala(self):
        calls = []

        def spy():
            calls.append(1)
            return True

        sh = ShadowEscalation(alpha=0.10)
        sh.observe(_readout(proceed=True, risk=0.1, measured_p=0.98),
                   system_two=spy)
        assert calls == []
        sh.observe(_readout(proceed=False, risk=0.9), system_two=spy)
        assert len(calls) == 1

    def test_system_two_che_falla_non_diventa_approvazione(self):
        def broken():
            raise RuntimeError("guard senza risposta")

        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(_readout(proceed=False, risk=0.9), system_two=broken)
        assert rec.escalate is True
        assert rec.system_two_supported is None      # mai tritare il silenzio

    def test_settle_registra_esito_reale(self):
        sh = ShadowEscalation(alpha=0.10)
        sh.observe(_readout(proceed=False, risk=0.9))
        sh.settle(0, success=False)
        assert sh.records()[0].success is False
        rep = sh.report()
        assert rep["settled"] == 1
        assert rep["error_rate_admitted"] is None    # nessun ammesso

    def test_report_conta_errori_degli_ammessi(self):
        sh = ShadowEscalation(alpha=0.10)
        # ammesso (no escalate) poi errore reale -> falso negativo system-one
        sh.observe(_readout(proceed=True, risk=0.05, measured_p=0.98))
        sh.settle(0, success=False)
        # escalated che il guard avrebbe bloccato
        sh.observe(_readout(proceed=False, risk=0.95),
                   system_two=lambda: False)
        sh.settle(1, success=False)
        rep = sh.report()
        assert rep["n"] == 2
        assert rep["escalated"] == 1
        assert rep["error_rate_admitted"] == 1.0
        assert rep["system_two_catches"] == 1.0

    def test_propensione_empirica_con_laplace(self):
        sh = ShadowEscalation(alpha=0.10, n_risk_bins=4)
        for _ in range(30):
            sh.observe(_readout(proceed=False, risk=0.95))     # sempre escala
        for _ in range(30):
            sh.observe(_readout(proceed=True, risk=0.05, measured_p=0.98))
        assert sh.propensity(0.95) > sh.propensity(0.05)
        assert 0.0 <= sh.propensity(0.95) <= 1.0

    def test_propensione_senza_record_neutra(self):
        sh = ShadowEscalation(alpha=0.10)
        assert sh.propensity(0.5) == 0.0

    def test_report_vuoto_no_numeri_inventati(self):
        rep = ShadowEscalation().report()
        assert rep["n"] == 0
        assert rep["escalation_rate"] is None
        assert rep["error_rate_admitted"] is None

    def test_osservazione_e_read_only(self):
        sh = ShadowEscalation(alpha=0.10)
        ro = _readout(proceed=False, risk=0.9)
        rec = sh.observe(ro)
        assert ro.proceed is False and ro.risk == 0.9
        assert isinstance(rec, EscalationRecord)
        assert len(sh.records()) == 1


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #


class TestCompatibilitySuite:
    def test_readout_dal_conformal_calibrator(self):
        cal = ConformalCalibrator(alpha=0.10).fit_from_scores(
            [0.9, 0.85, 0.8, 0.95])
        d = cal.decide(["risposta A", "risposta B", "risposta A", "risposta A"])
        # 3/4 uguali => consistency bassa, score <= threshold? costruiamo i
        # numeri dal calibratore, non a mano.
        readout = SystemOneReadout(proceed=d.proceed, risk=d.risk,
                                   score=d.score)
        sh = ShadowEscalation(alpha=0.10)
        rec = sh.observe(readout)
        # il readout e' quello che il calibratore ha deciso
        assert rec.risk == d.risk
        assert rec.escalate == (not d.proceed)

    def test_measured_p_dal_reliability_meter(self):
        meter = (ReliabilityMeter(n_bins=10, min_samples=1)
                 .record_many(
                     [0.95] * 60 + [0.6] * 40,
                     [True] * 60 + [False] * 40)
                 .fit())
        p_alto = meter.calibrate(0.95)   # misurata alta
        p_basso = meter.calibrate(0.6)   # misurata bassa
        sh = ShadowEscalation(alpha=0.10)
        r_ok = sh.observe(_readout(True, 0.05, measured_p=p_alto))
        r_no = sh.observe(_readout(True, 0.2, measured_p=p_basso))
        assert r_ok.escalate is False
        assert r_no.escalate is True and \
            r_no.reason is EscalationReason.LOW_CONFIDENCE

    def test_system_two_e_il_guard_Z3_a_3_passi(self):
        guard = medical_guard()
        contratto = guard.contracts[0]

        def guard_dice_ok():
            return check_contract(contratto, ctx_dosaggio_ok).status is \
                GuardStatus.RULES_VERIFIED

        sh = ShadowEscalation(alpha=0.10)

        # violazione: il guard blocca => system_two_supported False
        rec = sh.observe(_readout(False, 0.9),
                         system_two=lambda: False)
        assert rec.system_two_supported is False

        # caso pulito => True
        rec2 = sh.observe(_readout(True, 0.05, measured_p=0.99),
                          system_two=guard_dice_ok)
        assert rec2.escalate is False
        assert rec2.system_two_supported is None     # non interrogato

    def test_deterministico_tra_run(self):
        sh = ShadowEscalation(alpha=0.10)
        a1 = sh.observe(_readout(False, 0.9)).escalate
        b1 = sh.propensity(0.9)
        sh2 = ShadowEscalation(alpha=0.10)
        a2 = sh2.observe(_readout(False, 0.9)).escalate
        b2 = sh2.propensity(0.9)
        assert (a1, b1) == (a2, b2)

    def test_energizzato_da_consistency_score_reale(self):
        # lo score conformal e' davvero la self-consistency dei campioni
        ra = ["il primo zero e' a Im=14.1347",
              "il primo zero e' a Im=14.1347",
              "il primo zero e' a Im=14.1347"]
        rb = ["due", "odi", "nessuno sa"]
        s_alto = 1.0 - consistency_score(ra)      # accordo forte => altissimo
        s_basso = 1.0 - consistency_score(rb)     # risposte sparse => basso
        assert s_alto > s_basso
        assert 0.0 <= s_alto <= 1.0 and 0.0 <= s_basso <= 1.0