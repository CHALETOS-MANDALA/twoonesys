"""Reverse engineering della calibrazione: dove vive l'errore che T corregge,
e se la calibrazione e' COMPONIBILE (T per condizione che si compongono).

Scompone la temperatura globale (T=3.947, RUN4) in temperature per fascia
sullo STESSO fit set (seed 42). Analisi esplorativa in-sample: il verdetto
fuori campione spetta a RUN5, pre-registrato a parte.

    python reverse_calibration.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

FIT_DIR = Path(__file__).resolve().parent / "run" / "run4_fit"
T_GLOBAL = 3.9473479908780384  # fittata da `rizzo calibrate`, RUN4


def nll(logits: list[float], label: int, T: float) -> float:
    vals = [x / T for x in logits]
    top = max(vals)
    return top + math.log(sum(math.exp(v - top) for v in vals)) - vals[label]


def fit_T(group: list[dict]) -> float:
    grid = [math.log(0.05) + i * math.log(400) / 240 for i in range(241)] + [0.0]
    best = min(grid, key=lambda lt: sum(
        nll(r["logits"], r["label_index"], math.exp(lt)) for r in group))
    return math.exp(best)


def calibrated_conf(logits: list[float], T: float) -> tuple[float, int]:
    vals = [x / T for x in logits]
    top = max(vals)
    ps = [math.exp(v - top) for v in vals]
    total = sum(ps)
    ps = [p / total for p in ps]
    chosen = max(range(len(ps)), key=lambda i: ps[i])
    return ps[chosen], chosen


def ece(group: list[dict], T: float) -> float:
    scored = [(c, chosen == r["label_index"])
              for r in group for (c, chosen) in [calibrated_conf(r["logits"], T)]]
    total = len(scored)
    out = 0.0
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        sel = [(c, o) for c, o in scored
               if lo <= c < hi or (b == 9 and c == 1.0)]
        if sel:
            acc = sum(1 for _, o in sel if o) / len(sel)
            conf = sum(c for c, _ in sel) / len(sel)
            out += len(sel) / total * abs(acc - conf)
    return out


def main() -> int:
    rows = [json.loads(line) for line in
            (FIT_DIR / "labeled_logits.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    meta = [json.loads(line) for line in
            (FIT_DIR / "labeled_logits.meta.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == len(meta), "fit set e meta disallineati"

    print("reverse engineering della calibrazione (fit set seed 42, in-sample)\n")
    header = ("fascia", "n", "T_fit", "NLL@T1", "NLL@Tfit",
              "ECE@T1", "ECE@Tglob", "ECE@Tfascia")
    print("{:<8}{:>4}{:>8}{:>9}{:>10}{:>9}{:>11}{:>13}".format(*header))
    per_fascia_T: dict[str, float] = {}
    for fascia in ("A", "B", "C"):
        group = [r for r, m in zip(rows, meta) if m["fascia"] == fascia]
        T = fit_T(group)
        per_fascia_T[fascia] = T
        nll1 = sum(nll(r["logits"], r["label_index"], 1.0) for r in group) / len(group)
        nllt = sum(nll(r["logits"], r["label_index"], T) for r in group) / len(group)
        print("{:<8}{:>4}{:>8.2f}{:>9.3f}{:>10.3f}{:>9.3f}{:>11.3f}{:>13.3f}".format(
            fascia, len(group), T, nll1, nllt,
            ece(group, 1.0), ece(group, T_GLOBAL), ece(group, T)))

    T_all = fit_T(rows)
    print(f"\nT globale ri-fittata per controllo: {T_all:.3f} (atteso ~3.947)")

    # componibilita': la calibrazione per-condizione composta batte la globale
    # sullo stesso insieme? (in-sample; il verdetto vero e' fuori campione)
    scored_cond = [(c, chosen == r["label_index"])
                   for r, m in zip(rows, meta)
                   for (c, chosen) in [calibrated_conf(r["logits"], per_fascia_T[m["fascia"]])]]
    total = len(scored_cond)
    ece_cond = 0.0
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        sel = [(c, o) for c, o in scored_cond if lo <= c < hi or (b == 9 and c == 1.0)]
        if sel:
            acc = sum(1 for _, o in sel if o) / len(sel)
            conf = sum(c for c, _ in sel) / len(sel)
            ece_cond += len(sel) / total * abs(acc - conf)
    print(f"ECE composta (T per fascia) sull'intero fit set: {ece_cond:.3f}")
    print(f"ECE globale  (T=3.947)  sull'intero fit set: {ece(rows, T_GLOBAL):.3f}")
    print(f"ECE nulla    (T=1)      sull'intero fit set: {ece(rows, 1.0):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
