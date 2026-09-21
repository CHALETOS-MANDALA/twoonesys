"""TEST NEL MONDO REALE — TWOONESYS fuori dal laboratorio.

Non Riemann. Non fasce A/B/C. Ticket reali (linguaggio umano), fatti
strutturali del sistema (ledger/verifica/grant), M4 soft, policy, mondo
osservato sul disco, ricevute firmate.

Pipeline misurata:
  ticket reale
    → engine (System One) decide
    → detector testuale vs strutturale (stesso M4)
    → policy (assi indipendenti dalla confidence)
    → azione / rifiuto
    → osservazione del MONDO (file esiste? contenuto?)
    → ricevuta firmata + record outcome

Uso (engine su :8017):
    python bridge/real_world_run.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT))

SANDBOX = ROOT / "bridge" / "sandbox_real"
RECEIPTS = ROOT / "bridge" / "receipts_real"
LOG = ROOT / "bridge" / "run_real" / "outcomes.jsonl"

from cascade import ActionDenied, guarded  # noqa: E402
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from detector_contract import StructuralFacts, structural_score, textual_score  # noqa: E402
from run7_eval import T_from_soft  # noqa: E402

# M4: stesse T del fit RUN7/8 (non ritunate sul reale)
T_PRESENT = 0.01
T_ABSENT = 100.0

TICKETS = [
    {
        "id": "T-1001",
        "ticket": (
            "Buongiorno, mi avete addebitato due volte il canone di ottobre "
            "(14,90 EUR). Ho lo screenshot del doppio movimento sulla carta. "
            "Voglio il rimborso entro oggi, sono tre giorni che scrivo in chat "
            "e nessuno risponde. Cliente #88421."
        ),
    },
    {
        "id": "T-1002",
        "ticket": (
            "L'app si chiude appena apro la sezione pagamenti. Android 14, "
            "versione 6.2.1. Non riesco a vedere le fatture. Urgente."
        ),
    },
    {
        "id": "T-1003",
        "ticket": (
            "Vorrei passare al piano Business e sapere se c'e' sconto annuale. "
            "Siamo in 12 in azienda. Chiamatemi al 333-... grazie."
        ),
    },
]

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


def calibrate(raw_conf: float, score: float) -> float:
    """M4 soft sulla confidenza grezza (approssimazione top-vs-resto, dichiarata)."""
    import math
    p = min(max(raw_conf, 1e-6), 1 - 1e-6)
    logit = math.log(p / (1 - p))
    T = max(T_from_soft(score, T_PRESENT, T_ABSENT), 1e-3)
    # stabile: evita overflow su logit/T
    x = max(min(logit / T, 60.0), -60.0)
    ex = math.exp(x)
    return ex / (ex + 1.0)


def verify_receipt(path: Path) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "cascade", "verify", str(path)],
        capture_output=True, text=True, cwd=str(ROOT / "harness"))
    return (out.stdout + out.stderr).strip()


def world_observes(path: Path, request_id: str) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("request_id") == request_id and path.stat().st_size > 0


def structural_for(ticket_id: str, *, evidence: bool) -> StructuralFacts:
    """Fatti del SISTEMA, non del testo.

    evidence=True: ledger ha verificato un doppio addebito (digest attaccato).
    evidence=False: nessuna verifica di sistema disponibile.
    """
    if evidence:
        return StructuralFacts(
            n=0,
            kernel_value_attached=True,
            kernel_value=f"ledger:duplicate_charge:{ticket_id}",
            verdict_ok=True,
            verdict_code="ledger_match",
            engine_status="ok",
            provenance_ok=True,
        )
    return StructuralFacts(
        n=0,
        kernel_value_attached=False,
        engine_status="insufficient_evidence",
        provenance_ok=True,
    )


def textual_for(ticket_text: str) -> float:
    """Baseline fragile: cerca scorciatoie lessicali nel ticket."""
    # riusa lo stesso scorer con 'truth' fittizio: parole tipiche di 'evidenza'
    # Se il cliente DICE di avere prova, il testuale crede che l'evidenza ci sia.
    fake_truth = "screenshot"
    others = ["fattura", "bug"]
    # boost manuale coerente con lo spirito del detector testuale
    s = textual_score(ticket_text.lower(), fake_truth, others)
    if "screenshot" in ticket_text.lower() or "verificato" in ticket_text.lower():
        s += 1.0
    if "non riesco" in ticket_text.lower() or "si chiude" in ticket_text.lower():
        s -= 0.5
    return s


def append_outcome(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)
    if LOG.exists():
        LOG.unlink()

    proposer = RizzoProposer(timeout=180.0)
    try:
        health = proposer.health()
    except RizzoBridgeError as exc:
        print(f"ENGINE GIU': {exc}")
        return 1
    print(f"engine: {health.get('status')}  "
          f"model={json.dumps(health.get('model', {}))[:80]}")
    print(f"mondo: sandbox={SANDBOX}")
    print(f"log:   {LOG}\n")

    # scenari: (ticket, structural_evidence, label descrizione)
    scenarios = [
        (TICKETS[0], True,
         "T-1001 rimborso: ledger ha verificato il doppio addebito"),
        (TICKETS[0], False,
         "T-1001 STESSO testo: ledger VUOTO (testo parla di screenshot, "
         "struttura dice assenza) — divergenza reale"),
        (TICKETS[1], False,
         "T-1002 bug app: nessuna evidenza di sistema allegata"),
        (TICKETS[2], False,
         "T-1003 sales: nessuna evidenza di sistema allegata"),
    ]

    @guarded(receipt_dir=RECEIPTS)
    def scrivi_triage(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    results = []
    for i, (ticket, has_evidence, desc) in enumerate(scenarios):
        print("=" * 64)
        print(f"CASO {i+1}: {desc}")
        state = {"ticket": ticket["ticket"], "cliente_ref": ticket["id"]}
        t0 = time.perf_counter()
        prop = proposer.propose(state, QUESTIONS, question="reparto")
        latency = (time.perf_counter() - t0) * 1000

        facts = structural_for(ticket["id"], evidence=has_evidence)
        s_t = textual_for(ticket["ticket"])
        s_s = structural_score(facts)
        conf_t = calibrate(prop.confidence, s_t)
        conf_s = calibrate(prop.confidence, s_s)

        print(f"  engine: {prop.value}  raw_p={prop.confidence:.4f}  "
              f"({latency:.0f} ms)")
        print(f"  detector testuale     s={s_t:+.2f}  → conf_M4={conf_t:.4f}")
        print(f"  detector strutturale  s={s_s:+.2f}  → conf_M4={conf_s:.4f}")

        request_id = f"real-{ticket['id']}-{'ev' if has_evidence else 'no'}-{i}"
        payload = {
            "request_id": request_id,
            "ticket_id": ticket["id"],
            "reparto": prop.value,
            "raw_confidence": prop.confidence,
            "conf_testuale_m4": conf_t,
            "conf_strutturale_m4": conf_s,
            "structural_facts": facts.to_dict(),
            "touched": datetime.now(timezone.utc).isoformat(),
        }
        target = SANDBOX / f"{request_id}.json"

        # azione DENTRO sandbox — policy indipendente dalla confidence
        rec = scrivi_triage(target, json.dumps(payload, indent=1, ensure_ascii=False))
        outcome = world_observes(target, request_id)
        print(f"  policy: authorized={rec.authorized}  "
              f"mondo_osserva={outcome}  file={target.is_file()}")
        v = verify_receipt(RECEIPTS / f"{rec.request_id}.json")
        print(f"  ricevuta: {v.splitlines()[0] if v else '?'}")

        record = {
            **payload,
            "scenario": desc,
            "s_testuale": s_t,
            "s_strutturale": s_s,
            "authorized": rec.authorized,
            "outcome": outcome,
            "selection_probability": 1.0,
            "label_source": "mechanical",
            "contract_digest": "twoonesys-real-world-v1",
            "outcome_contract": "scala/real-smoke@soglia=1",
            "action_chosen": "file_write_triage",
            "phase_note": {
                "structural_facts": "condition_observed",
                "action_chosen": "action_chosen",
                "outcome": "outcome_observed",
            },
        }
        append_outcome(record)
        results.append(record)

    # braccio rifiuto: STESSA decisione, fuori sandbox
    print("=" * 64)
    print("CASO POLICY: stessa decisione, path FUORI sandbox")
    prop = proposer.propose({"ticket": TICKETS[0]["ticket"]}, QUESTIONS,
                            question="reparto")
    with tempfile.TemporaryDirectory() as tmp:
        vietato = Path(tmp) / "exfil.json"
        try:
            scrivi_triage(vietato, json.dumps({"p": prop.confidence}))
            print("  ERRORE: non bloccato")
            return 1
        except ActionDenied as denied:
            print(f"  raw_p={prop.confidence:.4f} ma authorized="
                  f"{denied.receipt.authorized} — policy indipendente")
            out = RECEIPTS / f"blocked_{denied.receipt.request_id}.json"
            denied.receipt.save(out)
            print(f"  verifica rifiuto: {verify_receipt(out).splitlines()[0]}")

    print("\n" + "=" * 64)
    print("RIEPILOGO MONDO REALE")
    for r in results:
        print(f"  {r['ticket_id']} ev={r['structural_facts']['kernel_value_attached']}  "
              f"raw={r['raw_confidence']:.3f}  "
              f"M4_test={r['conf_testuale_m4']:.3f}  "
              f"M4_strutt={r['conf_strutturale_m4']:.3f}  "
              f"auth={r['authorized']} mondo={r['outcome']}")
    print(f"\nlog outcomes: {LOG}")
    print(f"ricevute:     {RECEIPTS}")
    print(f"sandbox:      {SANDBOX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
