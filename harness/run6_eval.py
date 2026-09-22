"""RUN6 — sopravvivenza fuori laboratorio (sola lettura sui logit gia raccolti).

Metodo: PREREGISTRAZIONE_RUN6_TWOONESYS.md.
Non modifica engine, banco, ne' rapporti precedenti.

    python run6_eval.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from reverse_calibration import calibrated_conf, nll
from run_twoonesys_run1 import FASCE, ZEROS_N, build_case, kernel_truth, truncate
from run5_eval import GRID, auc, hm_ci95, _ece

ROOT = Path(__file__).resolve().parent
FIT = ROOT / "run" / "run4_fit"
EVAL = ROOT / "run" / "run5_eval"
OUT = ROOT / "run" / "run6"
T_GLOBAL = 3.9473479908780384


def fit_T(group: list[dict]) -> float:
    best = min(GRID, key=lambda lt: sum(
        nll(r["logits"], r["label_index"], math.exp(lt)) for r in group))
    return math.exp(best)


def load(pair_dir: Path, name: str) -> tuple[list[dict], list[dict]]:
    rows = [json.loads(l) for l in (pair_dir / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    meta = [json.loads(l) for l in (pair_dir / f"{name}.meta.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == len(meta)
    return rows, meta


def detect_evidence(state: dict, truth_4dp: str) -> bool:
    text = str(state.get("rapporto", ""))
    return truth_4dp in text or "valore confermato" in text


def metrics(scored: list[tuple[float, bool]]) -> dict:
    scores = [s for s, _ in scored]
    outcomes = [o for _, o in scored]
    n1, n0 = sum(outcomes), len(outcomes) - sum(outcomes)
    a = auc(scores, outcomes)
    lo, hi = hm_ci95(a, n1, n0)
    return {"auc": round(a, 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
            "ece": round(_ece(scored), 4),
            "n": len(scored), "successi": n1, "fallimenti": n0}


def score_with_T(rows, conditions: list[str], T_map: dict[str, float]):
    out = []
    for r, cond in zip(rows, conditions):
        conf, chosen = calibrated_conf(r["logits"], T_map[cond])
        out.append((conf, chosen == r["label_index"]))
    return out


def main() -> int:
    fit_rows, fit_meta = load(FIT, "labeled_logits")
    eval_rows, eval_meta = load(EVAL, "eval_logits")

    T_per = {f: fit_T([r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f])
             for f in ("A", "B", "C")}
    T_bin = {"presente": T_per["A"], "assente": T_per["C"]}
    print(f"T_presente={T_bin['presente']:.4f}  T_assente={T_bin['assente']:.4f}")

    rng = random.Random(2026)
    truths = {n: kernel_truth(n) for n in ZEROS_N}
    oracle_cond, detected_cond, detect_ok = [], [], 0
    for index, m in enumerate(eval_meta):
        fascia, n = FASCE[index % 3], ZEROS_N[index % len(ZEROS_N)]
        assert fascia == m["fascia"] and n == m["n"]
        state, _, truth = build_case(fascia, n, rng, truths)
        det = "presente" if detect_evidence(state, truncate(truth)) else "assente"
        ora = "presente" if fascia in ("A", "B") else "assente"
        detected_cond.append(det)
        oracle_cond.append(ora)
        detect_ok += int(det == ora)
    print(f"accuratezza detector: {detect_ok}/{len(eval_meta)} "
          f"({detect_ok / len(eval_meta):.3f})")

    results = {}
    scored_fine = []
    for r, m in zip(eval_rows, eval_meta):
        conf, chosen = calibrated_conf(r["logits"], T_per[m["fascia"]])
        scored_fine.append((conf, chosen == r["label_index"]))
    results["oracolo_fine"] = metrics(scored_fine)
    results["oracolo_binario"] = metrics(score_with_T(eval_rows, oracle_cond, T_bin))
    results["rilevato"] = metrics(score_with_T(eval_rows, detected_cond, T_bin))
    results["globale"] = metrics([
        (calibrated_conf(r["logits"], T_GLOBAL)[0],
         calibrated_conf(r["logits"], T_GLOBAL)[1] == r["label_index"])
        for r in eval_rows])
    results["nulla"] = metrics([
        (calibrated_conf(r["logits"], 1.0)[0],
         calibrated_conf(r["logits"], 1.0)[1] == r["label_index"])
        for r in eval_rows])

    degr = {}
    for eps in (0.05, 0.10, 0.20):
        rng_c = random.Random(7)
        contaminated = list(detected_cond)
        n_flip = int(round(eps * len(contaminated)))
        idxs = list(range(len(contaminated)))
        rng_c.shuffle(idxs)
        for i in idxs[:n_flip]:
            contaminated[i] = ("assente" if contaminated[i] == "presente"
                               else "presente")
        degr[str(eps)] = metrics(score_with_T(eval_rows, contaminated, T_bin))

    print("\nrisultati:")
    for name, m in results.items():
        print(f"  {name:<16} AUC {m['auc']:.4f} {m['auc_ci95']}  ECE {m['ece']:.4f}")
    print("degradazione:")
    for eps, m in degr.items():
        print(f"  e={eps:<4}           AUC {m['auc']:.4f}  ECE {m['ece']:.4f}")

    control_ok = (results["oracolo_fine"]["auc"] >= 0.99
                  and abs(results["oracolo_fine"]["ece"] - 0.0691) < 0.02)
    r = results["rilevato"]
    sustained = bool(r["ece"] <= 0.10 and r["auc"] >= 0.70 and r["auc_ci95"][0] > 0.5)
    report = {
        "controllo_oracolo_riproduce_run5": control_ok,
        "accuratezza_detector": round(detect_ok / len(eval_meta), 4),
        "T": {k: round(v, 4) for k, v in T_bin.items()},
        "risultati": results,
        "degradazione": degr,
        "affermazione_sostenuta": sustained and control_ok,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "run6.analysis.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ncontrollo OK: {control_ok}")
    print(f"affermazione sostenuta: {report['affermazione_sostenuta']}")
    print(f"REPORT={out}")
    return 0 if control_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
