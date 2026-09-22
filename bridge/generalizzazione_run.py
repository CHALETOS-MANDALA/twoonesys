"""Generalizzazione mondo reale — esegue la batteria pre-registrata.

Metodo: bridge/PREREGISTRAZIONE_GENERALIZZAZIONE.md (congelata PRIMA).
Casi: bridge/gen_cases.py (n=24).

    python bridge/generalizzazione_run.py
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
sys.path.insert(0, str(ROOT / "bridge"))
sys.path.insert(0, str(ROOT / "pct"))
sys.path.insert(0, str(ROOT))

SANDBOX = ROOT / "bridge" / "sandbox_gen"
RECEIPTS = ROOT / "bridge" / "receipts_gen"
OUT_DIR = ROOT / "bridge" / "run_gen"
LOG = OUT_DIR / "outcomes.jsonl"
SUMMARY = OUT_DIR / "summary.json"

from cascade import ActionDenied, guarded  # noqa: E402
from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from detector_contract import label_from_score, structural_score, textual_score  # noqa: E402
from run7_eval import T_from_soft  # noqa: E402
from episode_contract import Episode, esito_da_pipeline  # noqa: E402
from gen_cases import anti_maria_ok, casi  # noqa: E402

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
    if "screenshot" in low or "verificat" in low or "prova" in low or "confirmed" in low:
        s += 1.0
    if "allegato" in low or "attached" in low:
        s += 0.5
    if "non riesco" in low or "si chiude" in low or "crash" in low:
        s -= 0.5
    return s


def verify_receipt(path: Path) -> bool:
    out = subprocess.run(
        [sys.executable, "-m", "cascade", "verify", str(path)],
        capture_output=True, text=True, cwd=str(ROOT / "harness"))
    line = (out.stdout + out.stderr).strip()
    return line.startswith("ok")


def main() -> int:
    battery = casi()
    assert len(battery) == 24, f"n deve essere 24, got {len(battery)}"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
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

    print("=" * 64)
    print("  GENERALIZZAZIONE mondo reale — batteria pre-registrata n=24")
    print("=" * 64)
    print(f"engine: {health.get('status')}")

    @guarded(receipt_dir=RECEIPTS)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    rows = []
    for c in battery:
        print(f"\n--- {c.id}  tipo={c.tipo} ---")
        ep = Episode(request_id=f"gen-{c.id}")
        ep.set_condition(
            ledger_evidenza=c.expect_structural_usable,
            ref_ordine=c.id,
            ticket_text_hash=c.id,
        )

        prop = proposer.propose(
            {"ticket": c.ticket, "ref": c.id}, QUESTIONS, question="reparto")
        s_t = textual_for(c.ticket)
        s_s = structural_score(c.facts)
        lab_s = label_from_score(s_s)
        m4_t = calibrate(prop.confidence, s_t)
        m4_s = calibrate(prop.confidence, s_s)

        print(f"  gold={c.gold_reparto}  pred={prop.value}  raw={prop.confidence:.4f}")
        print(f"  M4 t={m4_t:.4f} s={m4_s:.4f}  label_s={lab_s}")

        ep.set_action(
            reparto_scelto=prop.value,
            raw_confidence=prop.confidence,
            conf_testuale_m4=m4_t,
            conf_strutturale_m4=m4_s,
            selection_probability=float(prop.confidence),
        )

        payload = {
            "request_id": ep.request_id,
            "caso": c.id,
            "reparto": prop.value,
            "raw_confidence": prop.confidence,
        }
        target = SANDBOX / f"{ep.request_id}.json"
        rec = scrivi(target, json.dumps(payload, ensure_ascii=False))
        sandbox_ok = target.is_file() and rec.authorized
        receipt_ok = verify_receipt(RECEIPTS / f"{rec.request_id}.json")
        ep.set_executed(authorized=rec.authorized)

        outside_denied = None
        with tempfile.TemporaryDirectory() as tmp:
            try:
                scrivi(Path(tmp) / "x.json", json.dumps(payload))
                outside_denied = False
            except ActionDenied as d:
                outside_denied = True
                outp = RECEIPTS / f"blocked_{d.receipt.request_id}.json"
                d.receipt.save(outp)

        code = esito_da_pipeline(
            sandbox_ok=bool(sandbox_ok),
            outside_denied=outside_denied,
            ledger_evidenza=c.expect_structural_usable if c.tipo != "kill_strutturale" else False,
            structural_usable=lab_s,
        )
        ep.set_outcome(code, outcome_ok=bool(sandbox_ok and outside_denied))
        record = ep.to_record()
        tempi_ok = (
            record.get("t_condition_observed") is not None
            and record.get("t_action_chosen") is not None
            and record["t_condition_observed"] < record["t_action_chosen"]
        )
        contract_ok = bool(record.get("outcome_contract")) and (
            "outcome_magnitude" in record) and tempi_ok

        row = {
            "id": c.id,
            "tipo": c.tipo,
            "gold_reparto": c.gold_reparto,
            "gold_chiaro": c.gold_chiaro,
            "pred": prop.value,
            "routing_ok": (c.gold_reparto is not None and prop.value == c.gold_reparto),
            "raw": prop.confidence,
            "m4_t": m4_t,
            "m4_s": m4_s,
            "s_t": s_t,
            "s_s": s_s,
            "label_s": lab_s,
            "expect_structural_usable": c.expect_structural_usable,
            "structural_honest": (not lab_s) if not c.expect_structural_usable else lab_s,
            "sandbox_ok": bool(sandbox_ok),
            "receipt_ok": receipt_ok,
            "outside_denied": outside_denied,
            "contract_ok": contract_ok,
            "outcome_code": code,
            "maria_like": c.maria_like,
        }
        rows.append(row)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row | {"ticket": c.ticket[:200]},
                                ensure_ascii=False) + "\n")

    # --- metriche G1–G8 ---
    chiaro = [r for r in rows if r["gold_chiaro"]]
    g1_acc = sum(1 for r in chiaro if r["routing_ok"]) / len(chiaro)
    g1 = g1_acc >= 0.75

    must_reject = [r for r in rows if not r["expect_structural_usable"]]
    g2_rate = sum(1 for r in must_reject if not r["label_s"]) / len(must_reject)
    g2 = g2_rate >= 0.90

    div = [r for r in rows if r["tipo"] == "divergenza_ledger_vuoto"]
    g3 = all((r["m4_t"] - r["m4_s"]) >= 0.20 for r in div) and len(div) > 0

    ali = [r for r in rows if r["tipo"] == "allineato_ledger_pieno"]
    g4 = all(r["m4_s"] >= 0.90 and abs(r["m4_t"] - r["m4_s"]) <= 0.15
             for r in ali) and len(ali) > 0

    g5 = all(r["sandbox_ok"] for r in rows)
    g6 = all(r["outside_denied"] is True for r in rows)
    g7 = all(r["contract_ok"] for r in rows)
    g8, g8_detail = anti_maria_ok(battery)

    gates = {
        "G1_routing": {"pass": g1, "value": round(g1_acc, 4), "n": len(chiaro),
                       "soglia": ">=0.75"},
        "G2_strutturale_onesto": {"pass": g2, "value": round(g2_rate, 4),
                                  "n": len(must_reject), "soglia": ">=0.90"},
        "G3_divergenza": {"pass": g3, "n": len(div),
                          "deltas": [round(r["m4_t"] - r["m4_s"], 4) for r in div],
                          "soglia": "tutti delta>=0.20"},
        "G4_allineamento": {"pass": g4, "n": len(ali),
                            "m4_s": [round(r["m4_s"], 4) for r in ali],
                            "soglia": "tutti m4_s>=0.90 e |dt|<=0.15"},
        "G5_sandbox": {"pass": g5, "soglia": "100%"},
        "G6_deny": {"pass": g6, "soglia": "100%"},
        "G7_episodio": {"pass": g7, "soglia": "100%"},
        "G8_anti_maria": {"pass": g8, "detail": g8_detail, "soglia": "tpl>=8 maria<=2"},
    }
    sostenuta = all(g["pass"] for g in gates.values())

    summary = {
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "prereg": "bridge/PREREGISTRAZIONE_GENERALIZZAZIONE.md",
        "n": len(rows),
        "engine_status": health.get("status"),
        "model_source": (health.get("model") or {}).get("source"),
        "gates": gates,
        "affermazione_sostenuta": sostenuta,
        "failures": [k for k, v in gates.items() if not v["pass"]],
        "rows": rows,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                       encoding="utf-8")

    print("\n" + "=" * 64)
    print("  GATE  esito   dettaglio")
    for k, v in gates.items():
        mark = "PASS" if v["pass"] else "FAIL"
        print(f"  {k:<24} {mark:<5}  { {kk: vv for kk, vv in v.items() if kk != 'pass'} }")
    print("-" * 64)
    print(f"  AFFERMAZIONE: {'SOSTENUTA' if sostenuta else 'NON SOSTENUTA'}")
    print(f"  summary: {SUMMARY}")
    print("=" * 64)
    return 0 if sostenuta else 2


if __name__ == "__main__":
    raise SystemExit(main())
