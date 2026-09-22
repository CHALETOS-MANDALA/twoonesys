"""RUN7 — mappe di calibrazione a confronto (sola lettura, stessi logit).

Metodo: PREREGISTRAZIONE_RUN7_TWOONESYS.md.
Non modifica engine, banco, rapporti RUN2-6.

    python run7_eval.py
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
OUT = ROOT / "run" / "run7"
T_GLOBAL = 3.9473479908780384
LAMBDAS = (0.05, 0.1, 0.2, 0.5)
T_CLIP = (0.2, 5.0)
TAU_ABSTAIN = 0.5
SOFT_K = 2.0


def load(pair_dir: Path, name: str):
    rows = [json.loads(l) for l in (pair_dir / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    meta = [json.loads(l) for l in (pair_dir / f"{name}.meta.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == len(meta)
    return rows, meta


def fit_T(group, lam: float = 0.0, t_min: float = 0.01, t_max: float = 100.0):
    grid = [lt for lt in GRID if t_min <= math.exp(lt) <= t_max]
    if not grid:
        grid = GRID

    def obj(lt):
        T = math.exp(lt)
        mean = sum(nll(r["logits"], r["label_index"], T) for r in group) / len(group)
        return mean + lam * (lt ** 2)

    return math.exp(min(grid, key=obj))


def metrics(scored: list[tuple[float, bool]]) -> dict:
    scores = [s for s, _ in scored]
    outcomes = [o for _, o in scored]
    n1, n0 = sum(outcomes), len(outcomes) - sum(outcomes)
    a = auc(scores, outcomes) if n1 and n0 else float("nan")
    lo, hi = (hm_ci95(a, n1, n0) if n1 and n0 else (float("nan"), float("nan")))
    return {"auc": round(a, 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
            "ece": round(_ece(scored), 4), "n": len(scored),
            "successi": n1, "fallimenti": n0}


def evidence_score(text: str, truth: str, other_truths: list[str],
                   *, hide_truth: bool = False) -> float:
    s = 0.0
    if not hide_truth and truth in text:
        s += 1.0
    if "valore confermato" in text:
        s += 0.5
    if "non disponibile" in text or "ancora in corso" in text:
        s -= 1.0
    for ot in other_truths:
        if ot != truth and ot in text:
            s -= 0.3
    return s


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def T_from_soft(score: float, T_present: float, T_absent: float, k: float = SOFT_K) -> float:
    w = sigmoid(-k * score)  # score alto → w basso → T_present
    return math.exp(w * math.log(T_absent) + (1.0 - w) * math.log(T_present))


def rebuild_eval_states(meta, truths):
    rng = random.Random(2026)
    states = []
    for index, m in enumerate(meta):
        fascia, n = FASCE[index % 3], ZEROS_N[index % len(ZEROS_N)]
        assert fascia == m["fascia"] and n == m["n"]
        state, _, truth = build_case(fascia, n, rng, truths)
        states.append({"state": state, "truth": truncate(truth), "n": n,
                       "fascia": fascia, "text": str(state["rapporto"])})
    return states


def apply_map(rows, temps: list[float]) -> list[tuple[float, bool]]:
    out = []
    for r, T in zip(rows, temps):
        conf, chosen = calibrated_conf(r["logits"], T)
        out.append((conf, chosen == r["label_index"]))
    return out


def hard_label(score: float, tau: float = TAU_ABSTAIN) -> str:
    if abs(score) < tau:
        return "astieni"
    return "presente" if score > 0 else "assente"


def temps_for_map(map_id: str, scores: list[float], T_present: float,
                  T_absent: float, T_reg_present: float, T_reg_absent: float,
                  T2_present: float, T2_absent: float
                  ) -> tuple[list[float], dict]:
    info = {"astensioni": 0}
    temps = []
    for s in scores:
        if map_id == "M0":
            lab = "presente" if s > 0 else "assente"
            temps.append(T_present if lab == "presente" else T_absent)
        elif map_id == "M1":
            lab = "presente" if s > 0 else "assente"
            temps.append(T_reg_present if lab == "presente" else T_reg_absent)
        elif map_id == "M2":
            lab = "presente" if s > 0 else "assente"
            temps.append(T2_present if lab == "presente" else T2_absent)
        elif map_id == "M3":
            lab = hard_label(s)
            if lab == "astieni":
                temps.append(T_GLOBAL)
                info["astensioni"] += 1
            else:
                temps.append(T_present if lab == "presente" else T_absent)
        elif map_id == "M4":
            temps.append(T_from_soft(s, T_present, T_absent))
        elif map_id == "M5":
            lab = hard_label(s)
            if lab == "astieni":
                temps.append(T_GLOBAL)
                info["astensioni"] += 1
            else:
                temps.append(T_reg_present if lab == "presente" else T_reg_absent)
        else:
            raise ValueError(map_id)
    return temps, info


def contaminate_scores_flip(scores: list[float], eps: float, seed: int) -> list[float]:
    """Flip segno di una frazione eps (equivalente al flip etichetta hard)."""
    rng = random.Random(seed)
    out = list(scores)
    n_flip = int(round(eps * len(out)))
    idxs = list(range(len(out)))
    rng.shuffle(idxs)
    for i in idxs[:n_flip]:
        out[i] = -out[i] if out[i] != 0 else -1.0
    return out


def contaminate_hide_truth(states, truths_map, delta: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    other = [truncate(truths_map[n]) for n in ZEROS_N]
    scores = []
    for st in states:
        hide = rng.random() < delta
        scores.append(evidence_score(st["text"], st["truth"], other, hide_truth=hide))
    return scores


def main() -> int:
    fit_rows, fit_meta = load(FIT, "labeled_logits")
    eval_rows, eval_meta = load(EVAL, "eval_logits")
    truths = {n: kernel_truth(n) for n in ZEROS_N}
    states = rebuild_eval_states(eval_meta, truths)
    other = [truncate(truths[n]) for n in ZEROS_N]

    # --- fit M0 (NLL puro) e scelta λ per M1 sul SOLO fit set ---
    T0 = {}
    for f in ("A", "B", "C"):
        g = [r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f]
        T0[f] = fit_T(g, lam=0.0)
    T_present, T_absent = T0["A"], T0["C"]

    # λ scelto sul fit: media NLL_reg su A∪B∪C, tie-break |log T| minore
    best_lam, best_key = None, None
    T_reg_by_lam = {}
    for lam in LAMBDAS:
        Tlam = {f: fit_T([r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f],
                         lam=lam) for f in ("A", "B", "C")}
        T_reg_by_lam[lam] = Tlam
        # score di selezione: NLL medio a queste T + lam*(log T)^2 medio (già in fit)
        # usa NLL puro medio sul fit come qualità predittiva in-sample + distanza da 1
        nll_mean = 0.0
        n = 0
        dist = 0.0
        pen = 0.0
        for f in ("A", "B", "C"):
            g = [r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f]
            for r in g:
                nll_mean += nll(r["logits"], r["label_index"], Tlam[f])
                n += 1
            lt = math.log(Tlam[f])
            dist += abs(lt)
            pen += lt ** 2
        nll_mean /= n
        nll_reg = nll_mean + lam * (pen / 3.0)
        key = (nll_reg, dist)  # min NLL_reg, poi distanza da T=1
        if best_key is None or key < best_key:
            best_key, best_lam = key, lam
    T_reg = T_reg_by_lam[best_lam]
    T_reg_present, T_reg_absent = T_reg["A"], T_reg["C"]

    # M2: fit vincolato nella griglia [0.2, 5]
    T2 = {f: fit_T([r for r, m in zip(fit_rows, fit_meta) if m["fascia"] == f],
                   lam=0.0, t_min=T_CLIP[0], t_max=T_CLIP[1])
          for f in ("A", "B", "C")}
    T2_present, T2_absent = T2["A"], T2["C"]

    print(f"M0  T_present={T_present:.4f}  T_absent={T_absent:.4f}")
    print(f"M1  lambda={best_lam}  T_present={T_reg_present:.4f}  "
          f"T_absent={T_reg_absent:.4f}")
    print(f"    T per lambda: " + ", ".join(
        f"l={lam}:A={T_reg_by_lam[lam]['A']:.3f}/C={T_reg_by_lam[lam]['C']:.3f}"
        for lam in LAMBDAS))
    print(f"M2  T_present={T2_present:.4f}  T_absent={T2_absent:.4f}  "
          f"(vincolo {T_CLIP})")

    # scores puliti
    scores_clean = [evidence_score(st["text"], st["truth"], other) for st in states]

    maps = ("M0", "M1", "M2", "M3", "M4", "M5")
    results = {}
    for mid in maps:
        temps, info = temps_for_map(mid, scores_clean, T_present, T_absent,
                                    T_reg_present, T_reg_absent,
                                    T2_present, T2_absent)
        m = metrics(apply_map(eval_rows, temps))
        m["astensioni"] = info["astensioni"]
        results[mid] = {"pulito": m}

        # ε-label contamination
        degr = {}
        for eps in (0.05, 0.10, 0.20):
            sc = contaminate_scores_flip(scores_clean, eps, seed=7)
            temps_e, info_e = temps_for_map(mid, sc, T_present, T_absent,
                                            T_reg_present, T_reg_absent,
                                            T2_present, T2_absent)
            me = metrics(apply_map(eval_rows, temps_e))
            me["astensioni"] = info_e["astensioni"]
            degr[str(eps)] = me
        results[mid]["eps"] = degr

        # feature-drop
        fd = {}
        for delta in (0.1, 0.2):
            sc = contaminate_hide_truth(states, truths, delta, seed=11)
            temps_d, info_d = temps_for_map(mid, sc, T_present, T_absent,
                                            T_reg_present, T_reg_absent,
                                            T2_present, T2_absent)
            md = metrics(apply_map(eval_rows, temps_d))
            md["astensioni"] = info_d["astensioni"]
            fd[str(delta)] = md
        results[mid]["feature_drop"] = fd

    # controllo M0 ≈ RUN6
    m0 = results["M0"]["pulito"]
    control_ok = m0["auc"] >= 0.99 and abs(m0["ece"] - 0.0691) < 0.02

    print("\n=== PULITO ===")
    print(f"{'mappa':<6} {'AUC':>7} {'ECE':>7} {'astieni':>8}")
    for mid in maps:
        m = results[mid]["pulito"]
        print(f"{mid:<6} {m['auc']:7.4f} {m['ece']:7.4f} {m['astensioni']:8d}")

    print("\n=== eps=0.20 (flip etichetta) ===")
    print(f"{'mappa':<6} {'AUC':>7} {'ECE':>7}")
    for mid in maps:
        m = results[mid]["eps"]["0.2"]
        print(f"{mid:<6} {m['auc']:7.4f} {m['ece']:7.4f}")

    print("\n=== feature-drop delta=0.20 ===")
    print(f"{'mappa':<6} {'AUC':>7} {'ECE':>7} {'astieni':>8}")
    for mid in maps:
        m = results[mid]["feature_drop"]["0.2"]
        print(f"{mid:<6} {m['auc']:7.4f} {m['ece']:7.4f} {m['astensioni']:8d}")

    # affermazione §1
    baseline_ece_20 = results["M0"]["eps"]["0.2"]["ece"]
    winners = []
    for mid in maps:
        p, e20 = results[mid]["pulito"], results[mid]["eps"]["0.2"]
        ok_clean = p["ece"] <= 0.10 and p["auc"] >= 0.70
        ok_deg = ((e20["ece"] <= 0.10 or e20["ece"] < baseline_ece_20)
                  and e20["auc"] >= 0.85)
        if ok_clean and ok_deg:
            winners.append(mid)

    report = {
        "controllo_M0_run6": control_ok,
        "T_M0": {"presente": round(T_present, 4), "assente": round(T_absent, 4)},
        "T_M1": {"lambda": best_lam,
                 "presente": round(T_reg_present, 4),
                 "assente": round(T_reg_absent, 4)},
        "T_M2": {"presente": round(T2_present, 4), "assente": round(T2_absent, 4),
                 "clip": list(T_CLIP)},
        "risultati": results,
        "vincitori_affermazione": winners,
        "affermazione_sostenuta": bool(winners) and control_ok,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "run7.analysis.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ncontrollo M0: {control_ok}")
    print(f"vincitori: {winners or '(nessuno)'}")
    print(f"affermazione sostenuta: {report['affermazione_sostenuta']}")
    print(f"REPORT={out}")
    return 0 if control_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
