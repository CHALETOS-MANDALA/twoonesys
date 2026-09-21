"""TWOONESYS — prova tu stesso (mondo reale).

Incolla un ticket / testo vero. Decidi se il ledger di sistema ha evidenza.
Vedi: decisione engine, detector testuale vs strutturale, M4, policy, mondo.

    dalla radice TWOONESYS:
        python bridge/prova_tu.py
    oppure:
        bridge\\AVVIA_PROVA.bat
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


def read_multiline(prompt: str) -> str:
    print(prompt)
    print("  (scrivi il testo; riga vuota per terminare)\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        if line == "" and not lines:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def ask_yes_no(q: str, default: bool = False) -> bool:
    hint = "S/n" if default else "s/N"
    while True:
        a = input(f"{q} [{hint}]: ").strip().lower()
        if a == "" and default:
            return True
        if a == "" and not default:
            return False
        if a in ("s", "si", "y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        print("  rispondi s oppure n")


def run_once(proposer: RizzoProposer) -> None:
    text = read_multiline("Incolla il ticket / messaggio reale:")
    if not text:
        print("  (vuoto — annullo)")
        return
    evidenza = ask_yes_no(
        "Il LEDGER DI SISTEMA ha evidenza verificata per questo caso?\n"
        "  (s = fatto strutturale presente; n = ledger vuoto,\n"
        "   anche se il testo parla di screenshot/prove)",
        default=False)

    ref = f"prova-{int(datetime.now().timestamp())}"
    print("\n--- engine decide ---")
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
        print("  >>> DIVERGENZA: il testo e la struttura non concordano")

    SANDBOX.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)

    @guarded(receipt_dir=RECEIPTS)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    request_id = ref
    payload = {
        "request_id": request_id,
        "reparto": prop.value,
        "raw_confidence": prop.confidence,
        "conf_testuale_m4": c_t,
        "conf_strutturale_m4": c_s,
        "ledger_evidenza": evidenza,
        "ticket": text[:500],
        "touched": datetime.now(timezone.utc).isoformat(),
    }
    target = SANDBOX / f"{request_id}.json"

    print("\n--- policy: scrittura IN sandbox ---")
    rec = scrivi(target, json.dumps(payload, indent=1, ensure_ascii=False))
    mondo = target.is_file() and json.loads(
        target.read_text(encoding="utf-8")).get("request_id") == request_id
    print(f"  authorized={rec.authorized}  mondo_osserva={mondo}")
    print(f"  file: {target}")
    print(f"  ricevuta: {verify_receipt(RECEIPTS / f'{rec.request_id}.json')}")

    if ask_yes_no("Provare la STESSA scrittura FUORI sandbox? (deve fallire)",
                  default=True):
        print("\n--- policy: scrittura FUORI sandbox ---")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                scrivi(Path(tmp) / "no.json", json.dumps(payload))
                print("  ERRORE: non e' stata bloccata")
            except ActionDenied as d:
                print(f"  BLOCCATA  authorized={d.receipt.authorized}")
                out = RECEIPTS / f"blocked_{d.receipt.request_id}.json"
                d.receipt.save(out)
                print(f"  ricevuta deny: {verify_receipt(out)}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload | {
            "authorized": rec.authorized, "outcome": mondo,
            "s_testuale": s_t, "s_strutturale": s_s,
            "contract_digest": "twoonesys-prova-tu-v1",
        }, ensure_ascii=False) + "\n")
    print(f"\n  sessione loggata in {LOG}")


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
        print("oppure:       cd engine && uv run rizzo serve --size 4b --bits 8")
        return 1
    print(f"engine: {h.get('status')}\n")

    while True:
        run_once(proposer)
        if not ask_yes_no("\nAltro ticket?", default=True):
            break
        print()
    print("fine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
