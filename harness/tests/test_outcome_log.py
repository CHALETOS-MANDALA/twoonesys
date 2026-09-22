"""CASCADE - Passo 7: la disciplina di registrare gli esiti (outcome_log.py).

CorrectnessSuite: append JSONL, dedup per request_id, esiti indeterminati che
NON alimentano il misuratore, righe malformate contate (mai buttate in
silenzio), niente numeri inventati su log vuota.
CompatibilitySuite: il "restart" — una seconda istanza sulla stessa log
RICOSTRUISCE il ReliabilityMeter identico e le metriche sono deterministiche.
"""

import json

import pytest

from cascade.outcome_log import OutcomeLog, OutcomeRecord, replay_all
from cascade.reliability import ReliabilityMeter


def _rec(rid: str, *, raw: float = 0.9, measured: float | None = 0.88,
         escalated: bool = False, approved: bool = True,
         outcome: bool | None = True, touched: float = 1.0) -> OutcomeRecord:
    return OutcomeRecord(request_id=rid, action="file_write",
                         raw_confidence=raw, measured_p=measured,
                         escalated=escalated, approved=approved,
                         outcome=outcome, touched=touched)


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestCorrectnessSuite:
    def test_append_e_read_back_identici(self, tmp_path):
        p = tmp_path / "out.jsonl"
        log = OutcomeLog(p)
        for i in range(5):
            log.record(_rec(f"r{i}", raw=0.5 + 0.1 * i))
        again = OutcomeLog(p).load()
        assert again.size == 5
        assert [r.request_id for r in again.records()] == [f"r{i}" for i in range(5)]

    def test_in_memory_default_non_tocca_disco(self, tmp_path):
        log = OutcomeLog()
        log.record(_rec("r1"))
        assert log.size == 1
        assert not (tmp_path / "out.jsonl").exists()

    def test_dedup_ultima_riga_vince(self, tmp_path):
        p = tmp_path / "out.jsonl"
        OutcomeLog(p).record(_rec("r1", outcome=True))
        OutcomeLog(p).record(_rec("r1", outcome=False, touched=2.0))
        log = OutcomeLog(p).load()
        assert log.size == 1
        assert log.records()[0].outcome is False     # la conciliazione vince

    def test_outcome_none_non_alimenta_il_metro(self, tmp_path):
        p = tmp_path / "out.jsonl"
        log = OutcomeLog(p)
        log.record(_rec("a", outcome=True))
        log.record(_rec("b", outcome=None))           # Indeterminate: ignoto
        log.record(_rec("c", outcome=False))
        meter = log.replay_into(ReliabilityMeter())
        settled = list(log.settled())
        assert len(settled) == 2                      # b NON entra mai
        assert all(o in (True, False) for _, o in settled)
        assert meter.size == 2

    def test_righe_malformate_contate_non_sparite(self, tmp_path):
        p = tmp_path / "out.jsonl"
        p.write_text(_rec("ok").to_json() + "\n{not json}\n\nciào\n",
                     encoding="utf-8")
        log = OutcomeLog(p).load()
        assert log.size == 1
        assert log.bad_lines == 2

    def test_validazione_record(self):
        with pytest.raises(ValueError):
            OutcomeRecord(request_id="x", action="a", raw_confidence=1.5,
                          measured_p=None, escalated=False, approved=True,
                          outcome=True, touched=0.0)
        with pytest.raises(ValueError):
            OutcomeRecord(request_id="x", action="a", raw_confidence=0.5,
                          measured_p=0.5, escalated=False, approved=True,
                          outcome="si", touched=0.0)
        with pytest.raises(ValueError):
            OutcomeRecord(request_id="   ", action="a", raw_confidence=0.5,
                          measured_p=None, escalated=False, approved=True,
                          outcome=None, touched=0.0)

    def test_metrica_vuota_mai_inventata(self, tmp_path):
        log = OutcomeLog(tmp_path / "vuota.jsonl").load()
        m = log.metrics()
        assert m["n"] == 0 and m["settled"] == 0
        assert m["success_rate"] is None and m["mean_raw_confidence"] is None

    def test_metrica_conta_solo_esiti_noti(self, tmp_path):
        log = OutcomeLog(tmp_path / "o.jsonl")
        log.record(_rec("a", outcome=True))
        log.record(_rec("b", outcome=None, approved=False))
        log.record(_rec("c", outcome=False, approved=False))
        m = log.metrics()
        assert m["settled"] == 2
        assert m["approved"] == 1                    # solo il Succeeded
        assert m["success_rate"] == 0.5


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE: il restart ricostruisce la curva identica
# --------------------------------------------------------------------------- #


class TestCompatibilitySuite:
    def test_replay_ricostruisce_metro_identico(self, tmp_path):
        p = tmp_path / "out.jsonl"
        log = OutcomeLog(p)
        direct = ReliabilityMeter()
        for i in range(60):
            raw = 0.5 + (i % 50) / 100.0
            ok = raw > 0.7
            log.record(_rec(f"r{i}", raw=raw, outcome=ok))
            direct.record(raw, ok)
        direct.fit()
        rebuilt = OutcomeLog(p).load().replay_into(ReliabilityMeter())
        for c in (0.55, 0.72, 0.9, 0.97):
            assert abs(rebuilt.calibrate(c) - direct.calibrate(c)) < 1e-12

    def test_replay_all_ricostruisce_log_e_metro(self, tmp_path):
        p = tmp_path / "out.jsonl"
        for i in range(40):
            OutcomeLog(p).record(_rec(f"r{i}", raw=0.6 + i / 200.0,
                                      outcome=i % 3 != 0))
        log, meter = replay_all(p)
        assert log.size == 40
        assert meter.size == 40
        assert meter.size >= meter.min_samples

    def test_determinismo_tra_run(self, tmp_path):
        p = tmp_path / "out.jsonl"
        for i in range(50):
            OutcomeLog(p).record(_rec(f"r{i}", raw=0.5 + (i % 50) / 100.0,
                                      measured=0.8, outcome=bool(i % 2)))
        m1 = OutcomeLog(p).load().replay_into(ReliabilityMeter())
        m2 = OutcomeLog(p).load().replay_into(ReliabilityMeter())
        assert m1.calibrate(0.85) == m2.calibrate(0.85)
        assert m1.ece(calibrated=True) == m2.ece(calibrated=True)

    def test_serializzazione_json_roundtrip(self, tmp_path):
        rec = _rec("r1", raw=0.5, measured=None, outcome=None)
        assert OutcomeRecord.from_json(rec.to_json()) == rec