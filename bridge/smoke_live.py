"""Smoke test LIVE di TWOONESYS: engine vero su :8017 + harness vero.

NON e' un test della suite (quelli non toccano la rete): questo parla con
l'engine in ascolto e scrive un'azione vera in una cartella temporanea.

Uso:
    rizzo serve --size 1.7b --bits 8        # in un terminale
    python bridge\\smoke_live.py            # dalla radice TWOONESYS

Nota: con l'1.7B la policy e' allow_abstain=False (documentato dall'autore:
con l'astensione attiva sceglie "non so" quasi sempre). Col 4B la policy
di default (astensione attiva) torna sensata.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from cascade.integrated_workflow import IntegratedWorkflow
from cascade.outcome_log import OutcomeLog
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer

STATE = {"ticket": "Mi hanno addebitato due volte il canone di ottobre, "
                   "sono tre giorni che scrivo e nessuno risponde. Rimborso!"}

QUESTIONS = {
    "reparto": {
        "type": "choice",
        "instructions": "Quale reparto deve gestire questo ticket?",
        "options": [
            {"id": "billing", "description": "Pagamenti, fatture, rimborsi"},
            {"id": "technical", "description": "Bug, malfunzionamenti, outage"},
            {"id": "sales", "description": "Vendite, preventivi, contratti"},
        ],
        "policy": {"allow_abstain": False},
    },
    "urgente": {
        "type": "boolean",
        "instructions": "Il ticket trasmette urgenza?",
        "policy": {"allow_abstain": False},
    },
}


def main() -> int:
    proposer = RizzoProposer(timeout=180.0)  # prima richiesta: compila i kernel GPU

    print("== 1. health engine ==")
    try:
        health = proposer.health()
    except RizzoBridgeError as exc:
        print(f"ENGINE GIU': {exc}")
        return 1
    print(json.dumps(health, indent=1)[:400])

    print("\n== 2. proposta (choice, KV condivisa fra le domande) ==")
    proposal = proposer.propose(STATE, QUESTIONS, question="reparto")
    print(f"value={proposal.value}  confidence={proposal.confidence:.4f}  "
          f"status={proposal.status}")
    print(f"probabilita': {json.dumps(proposal.probabilities)}")
    print(f"model={proposal.model_id}  latenza={proposal.latency_ms:.0f} ms  "
          f"prompt_sha256={proposal.prompt_sha256[:12]}...")

    print("\n== 3. dentro l'harness (evidenza -> gate -> azione -> record) ==")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wf = IntegratedWorkflow(object(), log=OutcomeLog(tmp_path / "log.jsonl"),
                                action_root=tmp_path / "actions")
        result = wf.run_with_rizzo("smoke-1", "smista il ticket",
                                   ["rimborsi: il reparto billing gestisce "
                                    "addebiti doppi e storni"],
                                   proposer, state=STATE, questions=QUESTIONS,
                                   question="reparto")
        print(f"action_status={result.action_status}  "
              f"evidence_ok={result.evidence.verdict.ok}  "
              f"elapsed={result.elapsed_ms:.0f} ms")
        record = json.loads((tmp_path / "log.jsonl")
                            .read_text(encoding="utf-8").strip().splitlines()[-1])
        print("record:", json.dumps({k: record[k] for k in
                                     ("request_id", "action_chosen",
                                      "raw_confidence", "approved", "outcome",
                                      "escalated")}, indent=1))
        if result.action_receipt:
            print(f"ricevuta azione: {result.action_receipt[:16]}...")

    print("\nSMOKE OK: l'engine decide, l'harness registra. TWOONESYS respira.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
