"""RUN5 — valutazione della calibrazione CONDIZIONATA (per fascia).

Metodo congelato in PREREGISTRAZIONE_RUN5_TWOONESYS.md. Appaiata con RUN4:
stessa popolazione (seed 2026), stessi esiti (argmax invariante sotto
temperatura), diversa mappa di calibrazione.

    python run_twoonesys_run1.py --collect-logits run/run5_eval/eval_logits.jsonl --seed 2026 --count 120
    python run5_eval.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from reverse_calibration import calibrated_conf, ece, nll  # stesse funzioni, stesso codice

ROOT = Path(__file__).resolve().parent
FIT = ROOT / "run" / "run4_fit"
EVAL = ROOT / "run" / "run5_eval"
T_GLOBAL = 3.9473479908780384
# griglia estesa dichiarata in pre-registrazione §2 (i fit RUN4 erano ai bordi)
GRID = [math.log(0.01) + i * math.log(10_000) / 480 for i in range(481)] + [0.0]


def fit_T(group: list[dict]) -> float:
    best = min(GRID, key=lambda lt: sum(
        nll(r["logits"], r["label_index"], math.exp(lt)) for r in group))
    return math.exp(best)


def auc(scores: list[float], outcomes: list[bool]) -> float:
    pos = [s for s, o in zip(scores, outcomes) if o]
    neg = [s for s, o in zip(scores, outcomes) if not o]
    wins = ties = 0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1
            elif p == q:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def hm_ci95(a: float, n1: int, n0: int) -> tuple[float, float]:
    q1 = a / (2.0 - a)
    q2 = 2 * a * a / (1.0 + a)
    var = (a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0)
    half = 1.96 * (var ** 0.5)
    return max(0.0, a - half), min(1.0, a + half)


def load(pair_dir: Path, name: str) -> tuple[list[dict], list[dict]]:
    rows = [json.loads(l) for l in (pair_dir / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    meta = [json.loads(l) for l in (pair_dir / f"{name}.meta.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == len(meta)
    return rows, meta


def metrics(scored: list[tuple[float, bool]]) -> dict:
    scores = [s for s, _ in scored]
    outcomes = [o for _, o in scored]
    n1, n0 = sum(outcomes), len(outcomes) - sum(outcomes)
    a = auc(scores, outcomes)
    lo, hi = hm_ci95(a, n1, n0)
    import random
    rng = random.Random(42)
    a_b2 = auc([rng.random() for _ in scored], outcomes)
    return {"auc": round(a, 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
            "ece": round(_ece(scored), 4),
            "B0_ece": 0.0,  # predittore costante al tasso base: ECE 0 per costruzione
            "B2_auc": round(a_b2, 4)}


def main() -> int:
    fit_rows, fit_meta = load(FIT, "labeled_logits")
    eval_rows, eval_meta = load(EVAL, "eval_logits")

    T_per = {}
    for fascia in ("A", "B", "C"):
        group = [r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == fascia]
        T_per[fascia] = fit_T(group)
    print("temperature per condizione (fit seed 42, griglia estesa):")
    for f, T in T_per.items():
        print(f"  {f}: T = {T:.3f}")

    def score(T_map) -> list[tuple[float, bool]]:
        out = []
        for r, m in zip(eval_rows, eval_meta):
            T = T_map[m["fascia"]] if isinstance(T_map, dict) else T_map
            conf, chosen = calibrated_conf(r["logits"], T)
            out.append((conf, chosen == r["label_index"]))
        return out

    results = {}
    for name, T_map in (("condizionata", T_per), ("globale", T_GLOBAL), ("nulla", 1.0)):
        results[name] = metrics(score(T_map))

    print("\nvalutazione appaiata sulla popolazione seed 2026 (120 casi):")
    for name, m in results.items():
        print(f"  {name:<13} AUC {m['auc']:.4f} {m['auc_ci95']}  ECE {m['ece']:.4f}")

    cond = results["condizionata"]
    report = {"temperature_per_condizione": {k: round(v, 4) for k, v in T_per.items()},
              "risultati": results,
              "affermazione_sostenuta": bool(
                  cond["ece"] <= 0.10 and cond["auc"] >= 0.70
                  and cond["auc_ci95"][0] > 0.5)}
    out = EVAL / "run5.analysis.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\naffermazione sostenuta: {report['affermazione_sostenuta']}")
    print(f"REPORT={out}")
    return 0


def _ece(scored: list[tuple[float, bool]], bins: int = 10) -> float:
    total = len(scored)
    out = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, o) for c, o in scored if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if sel:
            acc = sum(1 for _, o in sel if o) / len(sel)
            conf = sum(c for c, _ in sel) / len(sel)
            out += len(sel) / total * abs(acc - conf)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
