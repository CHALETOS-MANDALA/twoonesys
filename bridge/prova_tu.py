"""TWOONESYS — prova tu stesso (mondo reale).

    bridge\\AVVIA_PROVA.bat
    oppure:  python bridge/prova_tu.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT))

SANDBOX = ROOT / "bridge" / "sandbox_prova"
RECEIPTS = ROOT / "bridge" / "receipts_prova"
LOG = ROOT / "bridge" / "run_prova" / "session.jsonl"

from cascade import ActionDenied, guarded  # noqa: E402
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from detector_contract import StructuralFacts, structural_score, textual_score  # noqa: E402
from run7_eval import T_from_soft  # noqa: E402

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

DEMO_TICKET = (
    "Ticket T-1001 — Rimborso doppio addebito\n\n"
    "Cliente: Maria Rossi\n"
    "Ordine: #88421\n\n"
    "Buongiorno, ieri mi sono stati addebitati due volte 49,90€ "
    "per lo stesso ordine.\n"
    "Ho allegato screenshot dell'estratto conto e della conferma d'ordine.\n"
    "Chiedo rimborso immediato del doppio addebito.\n"
    "Grazie."
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
    low = text.lower()
    if "screenshot" in low or "verificat" in low or "prova" in low:
        s += 1.0
    if "non riesco" in low or "si chiude" in low or "crash" in low:
        s -= 0.5
    return s


def facts_for(evidenza: bool, ref: str) -> StructuralFacts:
    if evidenza:
        return StructuralFacts(
            n=0, kernel_value_attached=True,
            kernel_value=f"ledger:verified:{ref}",
            verdict_ok=True, verdict_code="ledger_match", engine_status="ok")
    return StructuralFacts(
        n=0, kernel_value_attached=False,
        engine_status="insufficient_evidence")


def verify_receipt(path: Path) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "cascade", "verify", str(path)],
        capture_output=True, text=True, cwd=str(ROOT / "harness"))
    line = (out.stdout + out.stderr).strip().splitlines()
    return line[0] if line else "(nessun output)"


def ask_yes_no(q: str, default: bool = False) -> bool:
    hint = "S/n" if default else "s/N"
    while True:
        try:
            a = input(f"{q} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if len(a) > 8:
            print("  rispondi solo s oppure n")
            continue
        if a == "" :
            return default
        if a in ("s", "si", "y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        print("  rispondi s oppure n")


def read_ticket() -> str:
    print("Ticket:")
    print("  INVIO = usa DEMO  |  altrimenti incolla e chiudi con END\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not lines and line.strip() == "":
            return DEMO_TICKET
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def evaluate(proposer: RizzoProposer, text: str, evidenza: bool, label: str) -> dict:
    ref = f"prova-{int(datetime.now().timestamp())}-{label}"
    print(f"\n=== {label} ===")
    print(f"ledger evidenza: {'SI' if evidenza else 'NO (vuoto)'}")
    prop = proposer.propose({"ticket": text, "ref": ref}, QUESTIONS,
                            question="reparto")
    facts = facts_for(evidenza, ref)
    s_t = textual_for(text)
    s_s = structural_score(facts)
    c_t = calibrate(prop.confidence, s_t)
    c_s = calibrate(prop.confidence, s_s)

    print(f"  decisione:     {prop.value}")
    print(f"  raw conf:      {prop.confidence:.4f}")
    print(f"  testuale  s={s_t:+.2f}  → M4 {c_t:.4f}")
    print(f"  struttur. s={s_s:+.2f}  → M4 {c_s:.4f}")
    if abs(c_t - c_s) > 0.05:
        print("  >>> DIVERGENZA: testo e struttura non concordano")
    else:
        print("  (testuale e strutturale allineati)")

    return {
        "request_id": ref,
        "reparto": prop.value,
        "raw_confidence": prop.confidence,
        "conf_testuale_m4": c_t,
        "conf_strutturale_m4": c_s,
        "ledger_evidenza": evidenza,
        "ticket": text[:500],
        "s_testuale": s_t,
        "s_strutturale": s_s,
        "touched": datetime.now(timezone.utc).isoformat(),
    }


def write_sandbox(payload: dict) -> tuple:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)

    @guarded(receipt_dir=RECEIPTS)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    target = SANDBOX / f"{payload['request_id']}.json"
    print("\n--- scrittura IN sandbox ---")
    rec = scrivi(target, json.dumps(payload, indent=1, ensure_ascii=False))
    mondo = target.is_file() and json.loads(
        target.read_text(encoding="utf-8")).get("request_id") == payload["request_id"]
    print(f"  authorized={rec.authorized}  mondo_osserva={mondo}")
    print(f"  ricevuta: {verify_receipt(RECEIPTS / f'{rec.request_id}.json')}")

    print("\n--- scrittura FUORI sandbox (deve fallire) ---")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            scrivi(Path(tmp) / "no.json", json.dumps(payload))
            print("  ERRORE: non e' stata bloccata")
            denied = False
        except ActionDenied as d:
            print(f"  BLOCCATA  authorized={d.receipt.authorized}")
            out = RECEIPTS / f"blocked_{d.receipt.request_id}.json"
            d.receipt.save(out)
            print(f"  ricevuta deny: {verify_receipt(out)}")
            denied = True

    return rec, mondo, denied


def log_row(payload: dict, extra: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload | extra | {
            "contract_digest": "twoonesys-prova-tu-v2",
        }, ensure_ascii=False) + "\n")


def run_demo(proposer: RizzoProposer) -> None:
    text = DEMO_TICKET
    print("\n--- ticket DEMO ---")
    for ln in text.splitlines():
        print(f"  {ln}")
    print("------------------")
    print(
        "\nStesso ticket DUE volte:\n"
        "  1) ledger VUOTO  → aspettati DIVERGENZA\n"
        "  2) ledger PIENO  → aspettati allineamento"
    )

    p1 = evaluate(proposer, text, evidenza=False, label="A ledger VUOTO")
    p2 = evaluate(proposer, text, evidenza=True, label="B ledger PIENO")
    rec, mondo, denied = write_sandbox(p1)

    log_row(p1, {"authorized": rec.authorized, "outcome": mondo,
                 "outside_denied": denied, "pass": "A"})
    log_row(p2, {"authorized": rec.authorized, "outcome": mondo,
                 "outside_denied": denied, "pass": "B"})

    print("\n========== RIEPILOGO ==========")
    print(f"  A ledger vuoto:  testuale M4 {p1['conf_testuale_m4']:.3f}  "
          f"strutt. M4 {p1['conf_strutturale_m4']:.3f}")
    print(f"  B ledger pieno:  testuale M4 {p2['conf_testuale_m4']:.3f}  "
          f"strutt. M4 {p2['conf_strutturale_m4']:.3f}")
    print(f"  sandbox ok={mondo}   fuori bloccata={denied}")
    print(f"  log: {LOG}")
    print("===============================")


def run_free(proposer: RizzoProposer) -> None:
    text = read_ticket()
    if not text:
        print("  (vuoto — annullo)")
        return
    print("--- testo usato ---")
    for ln in text.splitlines():
        print(f"  {ln}")
    print("-------------------")
    evidenza = ask_yes_no(
        "Ledger di sistema ha evidenza verificata? (solo s/n)",
        default=False)
    payload = evaluate(proposer, text, evidenza,
                       label="libero-" + ("si" if evidenza else "no"))
    rec, mondo, denied = write_sandbox(payload)
    log_row(payload, {"authorized": rec.authorized, "outcome": mondo,
                      "outside_denied": denied})


def main() -> int:
    print("=" * 60)
    print("  TWOONESYS — prova nel mondo reale")
    print("  engine :8017  |  M4 soft  |  policy sandbox")
    print("=" * 60)
    proposer = RizzoProposer(timeout=180.0)
    try:
        h = proposer.health()
    except RizzoBridgeError as exc:
        print(f"\nENGINE NON RAGGIUNGIBILE: {exc}")
        print("Avvia prima:  bridge\\AVVIA_ENGINE.bat")
        return 1
    print(f"engine: {h.get('status')}\n")
    print("Scegli:")
    print("  1  = DEMO automatico (consigliato: INVIO)")
    print("  2  = ticket libero")
    try:
        scelta = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nannullato.")
        return 0
    if scelta in ("", "1"):
        run_demo(proposer)
    elif scelta == "2":
        run_free(proposer)
    else:
        print("scelta non valida")
        return 1
    print("\nfine. Finestra chiudibile.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrotto.")
        raise SystemExit(130)
