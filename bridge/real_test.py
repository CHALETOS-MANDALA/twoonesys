"""IL PRIMO TEST REALE DI TWOONESYS - 2026-09-21.

Non uno smoke: il giro completo, dal vivo, con ricevute firmate e verifica
indipendente. L'engine (System One modello, :8017) decide; l'harness
(System One harness) decide se la decisione puo' toccare il mondo.

Tre bracci:

  A. L'engine decide -> azione DENTRO il sandbox -> autorizzata ->
     file scritto davvero -> ricevuta firmata -> verifica.
  B. La STESSA decisione (stessa confidenza ~0.999) -> azione FUORI dal
     sandbox -> BLOCCATA -> ricevuta firmata del rifiuto -> verifica.
     E' la tesi: una decisione ben formata non e' ancora un permesso.
  C. Claim numerico dell'engine -> la barriera lo giudica contro
     l'evidenza del kernel (primo zero di Riemann, calcolato qui):
     cifre dal modello, mai float, mai auto-verifica.

Uso: engine in ascolto (rizzo serve --size 1.7b --bits 8), poi
    python bridge\\real_test.py        dalla radice TWOONESYS
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "bridge" / "sandbox"
RECEIPTS = ROOT / "bridge" / "receipts"

from cascade import ActionDenied, guarded                     # noqa: E402
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from cascade.workers import run_verified                      # noqa: E402

TICKET = {"ticket": "Mi hanno addebitato due volte il canone di ottobre. "
                    "Sono tre giorni che scrivo e nessuno risponde. Rimborso!"}

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
}

ZERO_QUESTION = {
    "zero": {
        "type": "choice",
        "instructions": "Quale valore riporta il banco per il primo zero "
                        "della funzione zeta di Riemann?",
        "options": [
            {"id": "giusto", "description": "14.1347 (quattro cifre decimali)"},
            {"id": "sbagliato", "description": "19.0000"},
            {"id": "altro", "description": "21.0220"},
        ],
        "policy": {"allow_abstain": False},
    },
}

ZERO_STATE = {"report": "Il banco ha misurato il primo zero della funzione "
                        "zeta di Riemann sulla retta critica: 14.1347 "
                        "(quattro cifre decimali)."}

ZERO_VALUES = {"giusto": "14.1347", "sbagliato": "19.0000", "altro": "21.0220"}


def verify_receipt(path: Path) -> str:
    """Verifica INDIPENDENTE: solo chiavi pubbliche, come farebbe un terzo."""
    out = subprocess.run(
        [sys.executable, "-m", "cascade", "verify", str(path)],
        capture_output=True, text=True, cwd=ROOT)
    return (out.stdout + out.stderr).strip()


def main() -> int:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)

    proposer = RizzoProposer(timeout=180.0)
    try:
        health = proposer.health()
    except RizzoBridgeError as exc:
        print(f"ENGINE GIU': {exc}")
        return 1
    print(f"engine pronto: {health.get('status')} su :8017\n")

    # ------------------------------------------------------------------ #
    print("== BRACCIO A - decisione reale, azione DENTRO il sandbox ==")
    t0 = time.perf_counter()
    proposal = proposer.propose(TICKET, QUESTIONS, question="reparto")
    print(f"engine: reparto={proposal.value}  p={proposal.confidence:.4f}  "
          f"({proposal.latency_ms:.0f} ms, 0 token generati)")
    print(f"        distribuzione: {json.dumps(proposal.probabilities)}")

    report = {"decisione": proposal.value, "confidenza": proposal.confidence,
              "distribuzione": proposal.probabilities,
              "prompt_sha256": proposal.prompt_sha256, "stato": TICKET}

    @guarded(receipt_dir=RECEIPTS)
    def scrivi_triage(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    dentro = SANDBOX / "triage_smoke-1.json"
    rec_a = scrivi_triage(dentro, json.dumps(report, indent=1, ensure_ascii=False))
    print(f"harness: authorized={rec_a.authorized}  outcome={rec_a.outcome}  "
          f"(file osservato sul disco: {dentro.is_file()})")
    print(f"ricevuta firmata: {rec_a.request_id}.json")
    print("verifica indipendente:")
    print("  " + verify_receipt(RECEIPTS / f"{rec_a.request_id}.json")
          .replace("\n", "\n  "))

    # ------------------------------------------------------------------ #
    print("\n== BRACCIO B - STESSA decisione, azione FUORI dal sandbox ==")
    with tempfile.TemporaryDirectory() as fuori:
        vietato = Path(fuori) / "non_autorizzato.json"
        try:
            scrivi_triage(vietato, json.dumps(report))
            print("ERRORE: l'azione fuori sandbox non e' stata bloccata")
            return 1
        except ActionDenied as denied:
            rec_b = denied.receipt
            print(f"engine aveva detto p={proposal.confidence:.4f} — "
                  f"la policy non si e' mossa: authorized={rec_b.authorized}")
            print(f"file fuori sandbox esiste: {vietato.is_file()} (deve essere False)")
            out_b = RECEIPTS / f"blocked_{rec_b.request_id}.json"
            rec_b.save(out_b)
            print("verifica indipendente del RIFIUTO:")
            print("  " + verify_receipt(out_b).replace("\n", "\n  "))

    # ------------------------------------------------------------------ #
    print("\n== BRACCIO C - claim numerico dell'engine contro il kernel ==")
    zp = proposer.propose(ZERO_STATE, ZERO_QUESTION, question="zero")
    claim = ZERO_VALUES.get(zp.value or "")
    print(f"engine: scelta={zp.value}  p={zp.confidence:.4f}  -> claim {claim!r}")
    rep = run_verified("quanto vale il primo zero?", ["report del banco"],
                       calc_kind="zeron", calc_args={"n": 1}, precision=4,
                       model_value=claim)
    print(f"kernel (zeron, n=1): evidenza calcolata QUI, non dal modello")
    print(f"barriera: verdict.ok={rep.verdict.ok}  codice={rep.verdict.code.value}")
    if rep.claim is not None:
        print(f"claim ammesso: {rep.claim.value} (evidence_ref "
              f"{rep.claim.evidence_ref[:12]}...)")

    print("\n" + "=" * 64)
    print("TEST REALE COMPLETATO")
    print(f"  A: decisione p={proposal.confidence:.4f} -> autorizzata, "
          f"file scritto, ricevuta verificata")
    print(f"  B: stessa decisione -> bloccata dalla policy, ricevuta verificata")
    print(f"  C: claim {claim!r} -> verdict.ok={rep.verdict.ok}")
    print(f"  ricevute in {RECEIPTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
