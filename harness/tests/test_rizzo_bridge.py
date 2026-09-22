"""Test del ponte TWOONESYS engine <-> workflow (engine simulato, nessuna rete).

Stesso patto di test_eni_bridge.py: `post_fn` iniettato, mai httpx vero.
Le risposte finte seguono response.schema.json dell'engine.
"""

import json

import pytest

from cascade.integrated_workflow import IntegratedWorkflow
from cascade.outcome_log import OutcomeLog
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer


def _uncertainty(top=0.87, unavailable=0.0):
    return {"top_probability": top, "entropy_nats": 0.4,
            "concentration": 0.8, "unavailable_probability": unavailable}


def _envelope(answer):
    return {"model": {"id": "spark-x2.5-4b-q8"}, "mode": "shared",
            "calibration": None, "timing": {"total_ms": 95},
            "answers": {"q": answer}}


def _choice_answer(status="ok", choice="billing"):
    return {"type": "choice", "status": status, "choice": choice,
            "probabilities": {"billing": 0.87, "technical": 0.12, "sales": 0.01},
            "option_logits": {}, "legend": {}, "uncertainty": _uncertainty(),
            "probability_status": "uncalibrated_conditional_option_scores",
            "temperature": 1.0, "prompt_sha256": "abc123", "input_tokens": 120}


CHOICE_QUESTION = {"q": {"type": "choice", "instructions": "Chi gestisce?",
                         "options": [{"id": "billing", "description": "Pagamenti"},
                                     {"id": "technical", "description": "Bug"},
                                     {"id": "sales", "description": "Vendite"}]}}


# --------------------------------------------------------------------- #
# estrazione della proposta
# --------------------------------------------------------------------- #

def test_choice_confidence_e_la_probabilita_della_scelta():
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(_choice_answer()))
    proposal = proposer.propose({"ticket": "addebito errato"}, CHOICE_QUESTION)
    assert proposal.value == "billing"
    assert proposal.confidence == pytest.approx(0.87)
    assert proposal.abstained is False
    assert proposal.model_id == "spark-x2.5-4b-q8"
    assert proposal.prompt_sha256 == "abc123"


def test_boolean_confidence_segue_il_valore_scelto():
    answer = {"type": "boolean", "status": "ok", "value": False,
              "probabilities": {"true": 0.08, "false": 0.92},
              "option_logits": {}, "legend": {},
              "uncertainty": _uncertainty(top=0.92),
              "probability_status": "uncalibrated_conditional_option_scores",
              "temperature": 1.0, "prompt_sha256": "def456", "input_tokens": 60,
              "probability_true_given_available": 0.08}
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(answer))
    proposal = proposer.propose("stato", {"q": {"type": "boolean",
                                                "instructions": "E' urgente?"}})
    assert proposal.value == "false"
    # p del valore SCELTO (false), non p(true)
    assert proposal.confidence == pytest.approx(0.92)


def test_numeric_produce_model_value_decimale_nudo():
    answer = {"type": "numeric", "status": "ok", "value": 71.8, "unit": "percent",
              "probabilities": {"A": 0.10, "B": 0.85, "C": 0.05},
              "option_logits": {}, "legend": {},
              "uncertainty": _uncertainty(top=0.85),
              "probability_status": "uncalibrated_conditional_option_scores",
              "temperature": 1.0, "prompt_sha256": "ghi789", "input_tokens": 80,
              "statistics_given_available": None,
              "values": {"A": 0, "B": 72.5, "C": 100},
              "support": [0.0, 100.0], "range_probabilities": {}}
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(answer))
    proposal = proposer.propose({"misura": 72.5},
                                {"q": {"type": "numeric", "instructions": "Leggi",
                                       "unit": "percent",
                                       "anchors": [{"value": 0, "description": "vuoto"},
                                                   {"value": 100, "description": "pieno"}]}})
    # claim barrier: l'ancora SCELTA (argmax), non la media pesata (71.8)
    assert proposal.model_value == "72.5"
    assert proposal.value == "71.8"
    assert proposal.confidence == pytest.approx(0.85)


def test_astensione_non_e_mai_un_valore():
    answer = _choice_answer(status="insufficient_evidence", choice=None)
    answer["uncertainty"] = _uncertainty(top=0.41, unavailable=0.59)
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(answer))
    proposal = proposer.propose("stato vuoto", CHOICE_QUESTION)
    assert proposal.value is None
    assert proposal.abstained is True
    assert proposal.status == "insufficient_evidence"


def test_engine_giu_errore_tipizzato_mai_prosecuzione_di_comodo():
    def _down(payload):
        raise ConnectionError("connection refused")

    proposer = RizzoProposer(post_fn=_down)
    with pytest.raises(RizzoBridgeError):
        proposer.propose("stato", CHOICE_QUESTION)


def test_risposta_senza_la_domanda_e_errore():
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(_choice_answer()))
    with pytest.raises(RizzoBridgeError):
        proposer.propose("stato", CHOICE_QUESTION, question="inesistente")


def test_to_agent_signal_porta_confidenza_reale():
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(_choice_answer()))
    proposal = proposer.propose({"ticket": "x"}, CHOICE_QUESTION)
    sig = proposal.to_agent_signal()
    assert sig.confidence == pytest.approx(0.87)
    assert sig.proposal["status"] == "ok"
    assert sig.proposal["probabilities"]["technical"] == pytest.approx(0.12)


# --------------------------------------------------------------------- #
# dentro il workflow: il braccio e l'astensione
# --------------------------------------------------------------------- #

def _workflow(tmp_path):
    return IntegratedWorkflow(object(), log=OutcomeLog(tmp_path / "log.jsonl"),
                              action_root=tmp_path / "actions")


def _last_record(tmp_path):
    line = (tmp_path / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(line)


def test_workflow_registra_identita_del_braccio_e_confidenza_reale(tmp_path):
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(_choice_answer()))
    wf = _workflow(tmp_path)
    wf.run_with_rizzo("req-1", "smista il ticket", ["doc sui pagamenti"],
                      proposer, state={"ticket": "addebito errato"},
                      questions=CHOICE_QUESTION)
    rec = _last_record(tmp_path)
    # il braccio e' la decisione, non il nome del modello (B3)
    assert rec["action_chosen"] == "billing"
    # confidenza reale dai logit, non 0.5 cablato
    assert rec["raw_confidence"] == pytest.approx(0.87)


def test_workflow_astensione_resta_bloccata(tmp_path):
    answer = _choice_answer(status="insufficient_evidence", choice=None)
    proposer = RizzoProposer(post_fn=lambda payload: _envelope(answer))
    wf = _workflow(tmp_path)
    result = wf.run_with_rizzo("req-2", "smista il ticket", [],
                               proposer, state={}, questions=CHOICE_QUESTION)
    rec = _last_record(tmp_path)
    # mai autorizzare un'astensione: il gate resta chiuso
    assert result.action_status == "blocked"
    assert rec["approved"] is False
    assert rec["outcome"] is False
