"""RUN8 — detector strutturale vs M4-soft testuale (appaiato).

Metodo: PREREGISTRAZIONE_RUN8_DETECTOR.md + EMENDAMENTO_RUN8_TOLLERANZE.
Variabile unica: il detector. Stesso M4, stessi logit in-lab, stessi esiti.

    python ood_cases.py          # genera e valida banco OOD
    python run8_eval.py          # lab + OOD (OOD richiede engine su :8017)
    python run8_eval.py --lab-only
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

from detector_contract import (
    StructuralFacts, label_from_score, structural_score, textual_score,
)
from ood_cases import OOD_TYPES, build_ood_bank, write_ood_bank
from reverse_calibration import calibrated_conf, nll
from run5_eval import GRID, auc, hm_ci95, _ece
from run7_eval import T_from_soft, rebuild_eval_states
from run_twoonesys_run1 import (
    FASCE, ZEROS_N, build_case, kernel_truth, make_question, truncate,
)

ROOT = Path(__file__).resolve().parent
FIT = ROOT / "run" / "run4_fit"
EVAL = ROOT / "run" / "run5_eval"
OUT = ROOT / "run" / "run8"

# M4 = soft con T di M0 (RUN7)
T_PRESENT = 0.01
T_ABSENT = 98.0995  # fit NLL puro RUN7
SOFT_K = 2.0

# tolleranze emendamento
LAB_ECE_MAX = 0.10
LAB_AUC_MIN = 0.70
LAB_DELTA_ECE_MAX = 0.0287
BOOT_B = 2000
BOOT_SEED = 8


def load(pair_dir: Path, name: str):
    rows = [json.loads(l) for l in (pair_dir / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    meta = [json.loads(l) for l in (pair_dir / f"{name}.meta.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == len(meta)
    return rows, meta


def fit_T0(fit_rows, fit_meta):
    def fit(group):
        best = min(GRID, key=lambda lt: sum(
            nll(r["logits"], r["label_index"], math.exp(lt)) for r in group))
        return math.exp(best)
    T = {f: fit([r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f])
         for f in ("A", "B", "C")}
    return T["A"], T["C"]


def conf_metrics(scored: list[tuple[float, bool]]) -> dict:
    scores = [s for s, _ in scored]
    outcomes = [o for _, o in scored]
    n1, n0 = sum(outcomes), len(outcomes) - sum(outcomes)
    a = auc(scores, outcomes) if n1 and n0 else float("nan")
    lo, hi = (hm_ci95(a, n1, n0) if n1 and n0 else (float("nan"), float("nan")))
    # Brier / NLL
    brier = sum((s - (1.0 if o else 0.0)) ** 2 for s, o in scored) / len(scored)
    nll_v = 0.0
    for s, o in scored:
        p = min(max(s, 1e-12), 1 - 1e-12)
        nll_v += -math.log(p if o else 1 - p)
    nll_v /= len(scored)
    return {"auc": round(a, 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
            "ece": round(_ece(scored), 4), "brier": round(brier, 4),
            "nll": round(nll_v, 4), "n": len(scored),
            "successi": n1, "fallimenti": n0}


def detector_metrics(scores: list[float], labels: list[bool]) -> dict:
    """AUROC/AUPRC threshold-free + confusion a s>0."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    # AUROC = AUC of score vs label
    auroc = auc(scores, labels) if pos and neg else float("nan")
    # AUPRC approx: average precision
    pairs = sorted(zip(scores, labels), key=lambda x: -x[0])
    tp = fp = 0
    precisions = []
    n_pos = sum(labels)
    for s, y in pairs:
        if y:
            tp += 1
            precisions.append(tp / (tp + fp))
        else:
            fp += 1
    auprc = sum(precisions) / n_pos if n_pos else float("nan")
    pred = [label_from_score(s) for s in scores]
    tp_ = sum(1 for p, y in zip(pred, labels) if p and y)
    tn_ = sum(1 for p, y in zip(pred, labels) if (not p) and (not y))
    fp_ = sum(1 for p, y in zip(pred, labels) if p and (not y))
    fn_ = sum(1 for p, y in zip(pred, labels) if (not p) and y)
    return {"auroc": round(auroc, 4), "auprc": round(auprc, 4),
            "confusion_s_gt_0": {"tp": tp_, "tn": tn_, "fp": fp_, "fn": fn_}}


def bootstrap_ece_diff(scored_a: list[tuple[float, bool]],
                       scored_b: list[tuple[float, bool]],
                       B: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """IC95 di ECE(a)-ECE(b) appaiato (stessi indici)."""
    assert len(scored_a) == len(scored_b)
    n = len(scored_a)
    rng = random.Random(seed)
    diffs = []
    for _ in range(B):
        idxs = [rng.randrange(n) for _ in range(n)]
        ea = _ece([scored_a[i] for i in idxs])
        eb = _ece([scored_b[i] for i in idxs])
        diffs.append(ea - eb)
    diffs.sort()
    lo = diffs[int(0.025 * B)]
    hi = diffs[int(0.975 * B)]
    return {"diff_ece": round(_ece(scored_a) - _ece(scored_b), 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "esclude_0_a_favore_di_b": bool(lo > 0)}


def lab_structural_facts(fascia: str, n: int, truth: str) -> StructuralFacts:
    """Fatti strutturali in-distribution: A/B evidenza attached; C no."""
    if fascia in ("A", "B"):
        return StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth,
            verdict_ok=True, verdict_code="claim_ok", engine_status="ok")
    return StructuralFacts(
        n=n, kernel_value_attached=False, engine_status="insufficient_evidence")


def apply_m4(rows, scores: list[float], Tp: float, Ta: float):
    out = []
    for r, s in zip(rows, scores):
        T = T_from_soft(s, Tp, Ta, k=SOFT_K)
        conf, chosen = calibrated_conf(r["logits"], T)
        out.append((conf, chosen == r["label_index"]))
    return out


def eval_lab(Tp: float, Ta: float) -> dict:
    fit_rows, fit_meta = load(FIT, "labeled_logits")
    eval_rows, eval_meta = load(EVAL, "eval_logits")
    # rifit T se diverso — usiamo i passati (M0)
    del fit_rows, fit_meta
    truths = {n: kernel_truth(n) for n in ZEROS_N}
    states = rebuild_eval_states(eval_meta, truths)
    other = [truncate(truths[n]) for n in ZEROS_N]

    scores_t, scores_s, labels = [], [], []
    for st in states:
        scores_t.append(textual_score(st["text"], st["truth"], other))
        facts = lab_structural_facts(st["fascia"], st["n"], st["truth"])
        scores_s.append(structural_score(facts))
        labels.append(st["fascia"] in ("A", "B"))

    scored_t = apply_m4(eval_rows, scores_t, Tp, Ta)
    scored_s = apply_m4(eval_rows, scores_s, Tp, Ta)
    m_t = conf_metrics(scored_t)
    m_s = conf_metrics(scored_s)
    d_t = detector_metrics(scores_t, labels)
    d_s = detector_metrics(scores_s, labels)
    delta_ece = m_s["ece"] - m_t["ece"]
    preserve = (m_s["ece"] <= LAB_ECE_MAX and m_s["auc"] >= LAB_AUC_MIN
                and delta_ece <= LAB_DELTA_ECE_MAX)
    return {
        "testuale": {"twoonesys": m_t, "detector": d_t},
        "strutturale": {"twoonesys": m_s, "detector": d_s},
        "delta_ece_strutt_minus_test": round(delta_ece, 4),
        "preservazione_lab": preserve,
    }


def collect_ood_logits(cases, Tp: float, Ta: float) -> dict:
    """Chiama l'engine sul TESTO OOD; outcome = claim vs truth strutturale."""
    from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer
    from cascade.workers import run_verified

    proposer = RizzoProposer(timeout=120.0)
    health = proposer.health()
    print(f"engine: {health.get('status')}")

    truths = {n: kernel_truth(n) for n in ZEROS_N}
    other_all = {n: [truncate(truths[m]) for m in ZEROS_N if m != n]
                 for n in ZEROS_N}

    records = []
    for i, case in enumerate(cases):
        # anchors: truth + other + perturb (crescenti)
        close = case.truth
        far = truncate(truths[ZEROS_N[(ZEROS_N.index(case.n) + 2) % 5]])
        vals = sorted({case.truth, far, truncate(truths[ZEROS_N[0]])}, key=float)
        if len(vals) < 2:
            vals = [case.truth, far]
        anchors = [{"value": float(v), "description": "candidato"} for v in vals]
        state = {"rapporto": case.text}
        q = make_question(case.n, anchors)
        try:
            prop = proposer.propose(state, q, question="zero")
        except RizzoBridgeError as exc:
            records.append({"case_id": case.case_id, "null": True,
                            "null_reason": str(exc)})
            continue

        # outcome: se evidenza strutturale utilizzabile, claim deve matchare truth
        # se non utilizzabile, outcome=False (decidere senza evidenza e' fallimento
        # rispetto alla ground truth operativa del cancello)
        claim = prop.model_value
        if case.label_evidence_present and claim is not None:
            # barriera contro kernel reale
            rep = run_verified("zero?", ["r"], calc_kind="zeron",
                               calc_args={"n": case.n}, precision=4,
                               model_value=claim)
            outcome = bool(rep.verdict.ok)
        else:
            # senza evidenza utilizzabile: successo solo se il modello si astiene
            # — qui allow_abstain=false, quindi outcome=False per costruzione
            # quando gt dice assenza (il cancello non doveva autorizzare un claim)
            outcome = False

        option_logits = prop.raw.get("option_logits") or {}
        # ricostruisci vettore logit nell'ordine anchors + special
        order = [str(j) for j in range(len(anchors))]
        order += [k for k in option_logits if k not in order]
        logits = [float(option_logits[k]) for k in order if k in option_logits]
        # label_index = posizione del truth negli anchors (se presente)
        label_index = next((j for j, a in enumerate(anchors)
                            if abs(a["value"] - float(case.truth)) < 1e-9), 0)

        s_t = textual_score(case.text, case.truth, other_all[case.n])
        s_s = structural_score(case.facts)
        # confidenze M4
        row = {"logits": logits, "label_index": label_index}
        # per calibrated_conf usiamo chosen==label come proxy SOLO se gt present;
        # l'outcome operativo e' quello calcolato sopra
        conf_t, _ = calibrated_conf(logits, T_from_soft(s_t, Tp, Ta))
        conf_s, _ = calibrated_conf(logits, T_from_soft(s_s, Tp, Ta))

        records.append({
            "case_id": case.case_id, "ood_type": case.ood_type, "null": False,
            "label_evidence_present": case.label_evidence_present,
            "s_testuale": s_t, "s_strutturale": s_s,
            "conf_testuale": conf_t, "conf_strutturale": conf_s,
            "outcome": outcome, "claim": claim,
            "divergence": case.divergence,
        })
        if (i + 1) % 16 == 0:
            print(f"  OOD {i+1}/{len(cases)}")
        time.sleep(0.01)
    return {"model": health.get("model"), "records": records}


def eval_ood(records: list[dict]) -> dict:
    valid = [r for r in records if not r.get("null")]
    scored_t = [(r["conf_testuale"], r["outcome"]) for r in valid]
    scored_s = [(r["conf_strutturale"], r["outcome"]) for r in valid]
    labels = [r["label_evidence_present"] for r in valid]
    m_t = conf_metrics(scored_t)
    m_s = conf_metrics(scored_s)
    d_t = detector_metrics([r["s_testuale"] for r in valid], labels)
    d_s = detector_metrics([r["s_strutturale"] for r in valid], labels)
    boot = bootstrap_ece_diff(scored_t, scored_s)
    # per tipo
    per_type = {}
    for t in OOD_TYPES:
        sub = [r for r in valid if r["ood_type"] == t]
        if not sub:
            continue
        per_type[t] = {
            "n": len(sub),
            "ece_testuale": conf_metrics(
                [(r["conf_testuale"], r["outcome"]) for r in sub])["ece"],
            "ece_strutturale": conf_metrics(
                [(r["conf_strutturale"], r["outcome"]) for r in sub])["ece"],
        }
    return {
        "n_valid": len(valid), "n_null": len(records) - len(valid),
        "testuale": {"twoonesys": m_t, "detector": d_t},
        "strutturale": {"twoonesys": m_s, "detector": d_s},
        "bootstrap_ece_diff_testuale_minus_strutt": boot,
        "per_tipo": per_type,
    }


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--lab-only", action="store_true")
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    fit_rows, fit_meta = load(FIT, "labeled_logits")
    Tp, Ta = fit_T0(fit_rows, fit_meta)
    print(f"M4 T_present={Tp:.4f} T_absent={Ta:.4f}")

    print("\n== LAB (seed 2026, appaiato) ==")
    lab = eval_lab(Tp, Ta)
    print(f"  testuale    ECE {lab['testuale']['twoonesys']['ece']}  "
          f"AUC {lab['testuale']['twoonesys']['auc']}")
    print(f"  strutturale ECE {lab['strutturale']['twoonesys']['ece']}  "
          f"AUC {lab['strutturale']['twoonesys']['auc']}")
    print(f"  delta ECE   {lab['delta_ece_strutt_minus_test']}")
    print(f"  preservazione lab: {lab['preservazione_lab']}")

    ood_report = None
    if not args.lab_only:
        print("\n== OOD bank ==")
        cases = build_ood_bank()
        write_ood_bank(OUT / "ood_bank.jsonl", cases)
        print(f"  {len(cases)} casi validati")
        print("\n== OOD eval (engine) ==")
        blob = collect_ood_logits(cases, Tp, Ta)
        (OUT / "ood_records.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in blob["records"])
            + "\n", encoding="utf-8")
        ood_report = eval_ood(blob["records"])
        print(f"  validi={ood_report['n_valid']} nulli={ood_report['n_null']}")
        print(f"  testuale    ECE {ood_report['testuale']['twoonesys']['ece']}  "
              f"AUC {ood_report['testuale']['twoonesys']['auc']}")
        print(f"  strutturale ECE {ood_report['strutturale']['twoonesys']['ece']}  "
              f"AUC {ood_report['strutturale']['twoonesys']['auc']}")
        boot = ood_report["bootstrap_ece_diff_testuale_minus_strutt"]
        print(f"  bootstrap diff ECE test-strutt: {boot['diff_ece']} "
              f"IC95 {boot['ci95']} esclude0={boot['esclude_0_a_favore_di_b']}")

    # H1
    h1 = False
    if ood_report:
        boot = ood_report["bootstrap_ece_diff_testuale_minus_strutt"]
        ece_s = ood_report["strutturale"]["twoonesys"]["ece"]
        ece_t = ood_report["testuale"]["twoonesys"]["ece"]
        h1 = (lab["preservazione_lab"]
              and boot["esclude_0_a_favore_di_b"]
              and ece_s <= ece_t)

    report = {
        "T_m4": {"presente": Tp, "assente": Ta},
        "lab": lab,
        "ood": ood_report,
        "H1_sostenuta": h1,
        "H0_rifiutata": h1,
    }
    out = OUT / "run8.analysis.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nH1 sostenuta: {h1}")
    print(f"REPORT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
