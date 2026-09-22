"""TWOONESYS E2E — fusione CONOSCENZA + TECNOLOGIA.

Cerchio:

  ticket
    → System-One engine          [tecnologia]
    → decision + raw confidence  [tecnologia]
    → evidence/state detector    [tecnologia]
    → M4 calibration             [tecnologia]
    → policy → execution         [tecnologia]
    → receipt                    [tecnologia]
    → observed outcome           [tecnologia]
    → episodio (ScalaCosti+Tempi)[conoscenza]
    → PCT detector        [conoscenza]
    → consiglio stato futuro     [conoscenza]

Poi: kill suite (quanto e' difficile mentire al sistema).

    python bridge/e2e_chiudi.py
    bridge\\AVVIA_E2E.bat
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pct"))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "bridge"))
sys.path.insert(0, str(ROOT))

SANDBOX = ROOT / "bridge" / "sandbox_e2e"
RECEIPTS = ROOT / "bridge" / "receipts_e2e"
EPISODES = ROOT / "bridge" / "run_e2e" / "episodes.jsonl"
SUMMARY = ROOT / "bridge" / "run_e2e" / "e2e_summary.json"

from cascade import ActionDenied, guarded  # noqa: E402
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from detector_contract import StructuralFacts, structural_score, textual_score  # noqa: E402
from run7_eval import T_from_soft  # noqa: E402
from episode_contract import Episode, esito_da_pipeline  # noqa: E402
from adapter_episodi import diagnostica_episodi  # noqa: E402
from detector import Stato  # noqa: E402

T_PRESENT, T_ABSENT = 0.01, 100.0

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

TICKET = (
    "Ticket T-1001 — Rimborso doppio addebito\n"
    "Cliente: Maria Rossi\nOrdine: #88421\n"
    "Doppio addebito. Ho allegato screenshot dell'estratto conto.\n"
    "Chiedo rimborso."
)


def calibrate(raw: float, score: float) -> float:
    import math
    p = min(max(raw, 1e-6), 1 - 1e-6)
    logit = math.log(p / (1 - p))
    T = max(T_from_soft(score, T_PRESENT, T_ABSENT), 1e-3)
    x = max(min(logit / T, 60.0), -60.0)
    ex = math.exp(x)
    return ex / (ex + 1.0)


def textual_for(text: str) -> float:
    s = textual_score(text.lower(), "screenshot", ["fattura", "bug"])
    if "screenshot" in text.lower() or "verificat" in text.lower():
        s += 1.0
    return s


def facts_for(evidenza: bool, ref: str) -> StructuralFacts:
    if evidenza:
        return StructuralFacts(
            n=1, kernel_value_attached=True,
            kernel_value=f"ledger:verified:{ref}",
            verdict_ok=True, verdict_code="ledger_match", engine_status="ok")
    return StructuralFacts(
        n=0, kernel_value_attached=False,
        engine_status="insufficient_evidence")


def verify_receipt(path: Path) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "cascade", "verify", str(path)],
        capture_output=True, text=True, cwd=str(ROOT / "harness"))
    lines = (out.stdout + out.stderr).strip().splitlines()
    return lines[0] if lines else "(nessun output)"


def append_episode(rec: dict) -> None:
    EPISODES.parent.mkdir(parents=True, exist_ok=True)
    with EPISODES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_pass(proposer: RizzoProposer, *, evidenza: bool, label: str) -> dict:
    ref = "88421"
    ep = Episode(request_id=f"e2e-{label}-{int(datetime.now().timestamp())}")
    th = hashlib.sha256(TICKET.encode()).hexdigest()[:16]

    # T0 — condizione PRIMA della decisione
    ep.set_condition(
        ledger_evidenza=evidenza,
        ref_ordine=ref,
        ticket_text_hash=th,
    )

    print(f"\n=== PASS {label}  ledger={'SI' if evidenza else 'VUOTO'} ===")
    prop = proposer.propose(
        {"ticket": TICKET, "ref": ref}, QUESTIONS, question="reparto")
    facts = facts_for(evidenza, ref)
    s_t = textual_for(TICKET)
    s_s = structural_score(facts)
    c_t = calibrate(prop.confidence, s_t)
    c_s = calibrate(prop.confidence, s_s)

    # raw conf resta visibile — lezione centrale
    print(f"  decisione:     {prop.value}")
    print(f"  raw conf:      {prop.confidence:.4f}   ← non nascondere")
    print(f"  testuale  s={s_t:+.2f}  → M4 {c_t:.4f}")
    print(f"  struttur. s={s_s:+.2f}  → M4 {c_s:.4f}")
    if abs(c_t - c_s) > 0.05:
        print("  >>> DIVERGENZA testo/struttura")

    ep.set_action(
        reparto_scelto=prop.value,
        raw_confidence=prop.confidence,
        conf_testuale_m4=c_t,
        conf_strutturale_m4=c_s,
        s_testuale=s_t,
        s_strutturale=s_s,
        selection_probability=float(prop.confidence),  # proxy dichiarato
    )

    SANDBOX.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)

    @guarded(receipt_dir=RECEIPTS)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    payload = {
        "request_id": ep.request_id,
        "reparto": prop.value,
        "raw_confidence": prop.confidence,
        "conf_strutturale_m4": c_s,
        "ledger_evidenza": evidenza,
    }
    target = SANDBOX / f"{ep.request_id}.json"
    rec = scrivi(target, json.dumps(payload, indent=1, ensure_ascii=False))
    sandbox_ok = target.is_file()
    ep.set_executed(authorized=rec.authorized, receipt_ok=True)
    print(f"  sandbox: authorized={rec.authorized} mondo={sandbox_ok}")
    print(f"  ricevuta: {verify_receipt(RECEIPTS / f'{rec.request_id}.json')}")

    outside_denied = None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            scrivi(Path(tmp) / "no.json", json.dumps(payload))
            outside_denied = False
            print("  fuori sandbox: ERRORE non bloccata")
        except ActionDenied as d:
            outside_denied = True
            out = RECEIPTS / f"blocked_{d.receipt.request_id}.json"
            d.receipt.save(out)
            print(f"  fuori sandbox: BLOCCATA  ({verify_receipt(out)})")

    structural_usable = s_s > 0
    code = esito_da_pipeline(
        sandbox_ok=sandbox_ok and rec.authorized,
        outside_denied=outside_denied,
        ledger_evidenza=evidenza,
        structural_usable=structural_usable,
    )
    if outside_denied and sandbox_ok:
        # esito composito: sandbox ok + deny fuori = OUTSIDE_DENIED_OK se ledger coerente
        if evidenza and structural_usable:
            code = "OUTSIDE_DENIED_OK"
        elif (not evidenza) and (not structural_usable):
            code = "LEDGER_EMPTY_CORRECT"
        else:
            code = "SANDBOX_WRITE_OK"

    ep.set_outcome(code, outcome_ok=sandbox_ok and bool(outside_denied))
    record = ep.to_record()
    append_episode(record)
    print(f"  outcome_code={code}  mag={record['outcome_magnitude']}  "
          f"contract={record['outcome_contract']}")
    return record


def run_kill() -> dict:
    print("\n=== KILL SUITE ===")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "bridge" / "kill_suite.py")],
        capture_output=True, text=True, cwd=str(ROOT))
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr[-500:])
    kill_path = ROOT / "bridge" / "run_e2e" / "kill_suite.json"
    if kill_path.is_file():
        return json.loads(kill_path.read_text(encoding="utf-8"))
    return {"error": "kill_suite.json mancante", "returncode": proc.returncode}


def main() -> int:
    print("=" * 64)
    print("  TWOONESYS E2E — conoscenza + tecnologia")
    print("=" * 64)

    proposer = RizzoProposer(timeout=180.0)
    try:
        h = proposer.health()
    except RizzoBridgeError as exc:
        print(f"ENGINE NON RAGGIUNGIBILE: {exc}")
        print("Avvia: bridge\\AVVIA_ENGINE.bat  (poi rilancia E2E)")
        return 1
    print(f"engine: {h.get('status')}")

    # reset episodi di questa sessione di chiusura
    EPISODES.parent.mkdir(parents=True, exist_ok=True)
    if EPISODES.is_file():
        EPISODES.write_text("", encoding="utf-8")

    a = run_pass(proposer, evidenza=False, label="A")
    b = run_pass(proposer, evidenza=True, label="B")
    kill = run_kill()

    print("\n=== CONOSCENZA: PCT sui nuovi episodi ===")
    diag, note = diagnostica_episodi(EPISODES)
    for n in note:
        print(f"  - {n}")
    for d in diag:
        print(f"  {d.fenomeno:<22} {d.stato.value:<16} {d.misura:.4f}")

    rilevati = [d.fenomeno for d in diag if d.stato is Stato.RILEVATO]
    non_oss = [d.fenomeno for d in diag if d.stato is Stato.NON_OSSERVABILE]
    if any(x in rilevati for x in ("effect_flip", "catastrophe")):
        futuro = "CONSERVA EPISODI"
    elif non_oss:
        futuro = "NON concludere assenza — campi/fenomeni ancora non osservabili a scala"
    else:
        futuro = "aggregato ok per ora; continua a scrivere episodi"

    summary = {
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "pilastri": {
            "tecnologia": "engine→raw→detector→M4→policy→exec→receipt→outcome",
            "conoscenza": "ScalaCosti+Tempi→episodio→PCT→stato futuro",
        },
        "pass_A": {
            "raw": a.get("raw_confidence"),
            "m4_t": a.get("conf_testuale_m4"),
            "m4_s": a.get("conf_strutturale_m4"),
            "outcome": a.get("outcome_code"),
        },
        "pass_B": {
            "raw": b.get("raw_confidence"),
            "m4_t": b.get("conf_testuale_m4"),
            "m4_s": b.get("conf_strutturale_m4"),
            "outcome": b.get("outcome_code"),
        },
        "kill": {
            "regge": kill.get("regge"),
            "kill_o_fallimenti": kill.get("kill_o_fallimenti"),
            "n": kill.get("n"),
        },
        "pct": {
            "rilevati": rilevati,
            "non_osservabili": non_oss,
            "note": note,
        },
        "stato_futuro": futuro,
        "dimostra": (
            "pipeline distingue dichiarazione testuale da stato strutturale "
            "e scrive episodi con i due campi che rendono PCT osservabile"
        ),
        "non_dimostra": (
            "generalizzazione sul mondo reale; 100 ticket-Maria non sono un benchmark"
        ),
        "episodes": str(EPISODES),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                       encoding="utf-8")

    print("\n========== CHIUSURA CERCHIO ==========")
    print(f"  A ledger vuoto:  M4 t={a.get('conf_testuale_m4'):.3f}  "
          f"s={a.get('conf_strutturale_m4'):.3f}  raw={a.get('raw_confidence'):.3f}")
    print(f"  B ledger pieno:  M4 t={b.get('conf_testuale_m4'):.3f}  "
          f"s={b.get('conf_strutturale_m4'):.3f}  raw={b.get('raw_confidence'):.3f}")
    print(f"  kill suite:      regge={kill.get('regge')}/{kill.get('n')}  "
          f"ferite={kill.get('kill_o_fallimenti')}")
    print(f"  stato futuro:    {futuro}")
    print(f"  summary:         {SUMMARY}")
    print("======================================")
    print("\nfine. Cerchio conoscenza+tecnologia chiuso nel percorso vivo.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrotto.")
        raise SystemExit(130)
