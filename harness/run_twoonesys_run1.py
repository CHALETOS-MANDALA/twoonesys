"""Run 2 di calibrazione - TWOONESYS engine come proponente.

Metodo CONGELATO in PREREGISTRAZIONE_RUN2_TWOONESYS.md (commit che la
introduce). Questo script implementa quel documento, nient'altro.

    pilota:  python run_twoonesys_run1.py --pilot
    run:     python run_twoonesys_run1.py
    analisi: python run_twoonesys_run1.py --analyze   (SOLO dopo 120/30)

L'oracolo: la verita' la calcola il kernel (zeron), mai hardcoded; il claim
nasce dall'engine (ancora scelta, argmax); outcome = verdict.ok della
barriera. Confidenza ed esito nascono da due fonti che non si toccano.

Tetto di sicurezza implementativo: 1000 tentativi (i nulli non contano come
decisioni valide; alzato da 250 perche' la contenzione VRAM di Ollama produce
nulli a raffica e il resume numera i tentativi in cumulato); il tetto
dichiarato resta 200 valide (doc §6).
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from cascade.workers import calc_evidence, run_verified           # noqa: E402

CONTRACT_DIGEST = "twoonesys-run2-v1"
ZEROS_N = (1, 2, 3, 4, 5)
FASCE = ("A", "B", "C")
VRAM_FLOOR_MIB = 2048  # RUN3 (4B residente): 1024, emendamento 2026-09-21 §2
PRECISION = 4
MAX_ATTEMPTS = 1000  # sicurezza anti-loop; i tetti dichiarati sono sui VALIDI


# --------------------------------------------------------------------- #
# utilita'
# --------------------------------------------------------------------- #

def vram_free_mib() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        return int(out.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return -1


def kernel_truth(n: int, digits: int = 15) -> str:
    """La verita' dal kernel, mai hardcoded: zero n-esimo, `digits` cifre."""
    ev = calc_evidence("zeron", n=n, digits=digits)
    return str(ev["fact"]["expected"][0]["value"])


def truncate(value_str: str, decimals: int = PRECISION) -> str:
    """Troncamento (mai arrotondamento): la barriera tollera il troncato."""
    if "." not in value_str:
        return value_str
    ip, fp = value_str.split(".", 1)
    fp = fp[:decimals].ljust(decimals, "0")
    return f"{ip}.{fp}"


def perturb_last_digit(value_str: str, delta: int) -> str:
    ip, fp = value_str.split(".", 1)
    last = (int(fp[-1]) + delta) % 10
    return f"{ip}.{fp[:-1]}{last}"


def build_case(fascia: str, n: int, rng: random.Random,
               truths: dict[int, str]) -> tuple[dict, list[dict], str]:
    """(stato, anchors, claim_vero_4dp). Gli anchor mescolati col seed."""
    truth = truncate(truths[n])
    m = ZEROS_N[(ZEROS_N.index(n) + 1) % len(ZEROS_N)]
    other = truncate(truths[m])
    close = perturb_last_digit(truth, rng.choice((-1, 1)))
    far = f"{float(truth) + rng.choice((-0.5, 0.5)):.4f}"

    if fascia == "A":
        state = {"rapporto": f"Rapporto di misura. Il banco ha determinato lo "
                             f"zero di Riemann numero {n} sulla retta critica: "
                             f"parte immaginaria {truths[n]}. Misura confermata, "
                             f"nessuna anomalia strumentale."}
        values = [truth, other, far]
    elif fascia == "B":
        state = {"rapporto": f"Rapporto di misura. Stima preliminare dello zero "
                             f"numero {n}: {close}. Dopo la verifica strumentale "
                             f"il valore confermato e' {truths[n]}. La stima "
                             f"preliminare e' da considerarsi superata."}
        values = [truth, close, other]
    else:  # C: il valore per n NON e' nel rapporto
        state = {"rapporto": f"Rapporto di misura. Il banco ha completato la "
                             f"misura dello zero di Riemann numero {m}: parte "
                             f"immaginaria {truths[m]}. Per lo zero numero {n} "
                             f"la misura e' ancora in corso: valore non "
                             f"disponibile in questo rapporto."}
        values = [truth, other, close]

    # schema engine: anchor strettamente crescenti (emendamento 2026-09-21:
    # niente shuffle; il bias di posizione lo varia il valore dei distrattori)
    anchors = [{"value": float(v),
                "description": "un possibile valore della parte immaginaria"}
               for v in sorted(set(values), key=float)]
    return state, anchors, truth


def make_question(n: int, anchors: list[dict]) -> dict:
    return {"zero": {
        "type": "numeric",
        "instructions": f"Quanto vale lo zero di Riemann numero {n} secondo "
                        f"questo rapporto (parte immaginaria, 4 cifre decimali)?",
        "unit": "im",
        "anchors": anchors,
        "policy": {"allow_abstain": False}}}


# --------------------------------------------------------------------- #
# il run
# --------------------------------------------------------------------- #

def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / ("pilot.jsonl" if args.pilot else f"{run_dir.name}.jsonl")
    valid = failures = start_attempt = 0
    if args.resume and log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            start_attempt = max(start_attempt,
                                int(str(r["request_id"]).rsplit("-", 1)[1]) + 1)
            if not r["null"]:
                valid += 1
                failures += 0 if r["outcome"] else 1
        print(f"resume: {valid} valide e {failures} fallimenti gia nel log, "
              f"riparto dal tentativo {start_attempt}")
    elif log_path.exists():
        log_path.unlink()

    proposer = RizzoProposer(timeout=120.0)
    health = proposer.health()
    model_id = json.dumps(health.get("model", {}))[:80]
    print(f"engine: {health.get('status')}  model={model_id}")

    rng = random.Random(args.seed)
    truths = {n: kernel_truth(n) for n in ZEROS_N}
    print(f"verita' dal kernel (n=1..5): {[truncate(t) for t in truths.values()]}")

    target = 20 if args.pilot else args.count
    nulls: list[dict] = []
    attempts = start_attempt

    while attempts < MAX_ATTEMPTS:
        # regola congelata §6: stop quando ENTRAMBE le condizioni sono soddisfatte
        if valid >= target and (args.pilot or failures >= args.min_failures):
            break
        if not args.pilot and valid >= 200:  # tetto dichiarato (doc §6)
            break
        fascia = FASCE[attempts % 3]
        n = ZEROS_N[attempts % len(ZEROS_N)]
        request_id = f"{run_dir.name}-{attempts:03d}"
        attempts += 1

        state, anchors, truth = build_case(fascia, n, rng, truths)
        vram = vram_free_mib()
        record = {"request_id": request_id, "fascia": fascia, "n": n,
                  "truth": truth, "selection_probability": 1.0,
                  "contract_digest": CONTRACT_DIGEST,
                  "label_source": "mechanical", "vram_free_mib": vram,
                  "null": False, "null_reason": ""}

        if 0 <= vram < args.vram_floor:
            record.update(null=True,
                          null_reason=f"vram {vram} < {args.vram_floor}")
        else:
            t0 = time.perf_counter()
            try:
                proposal = proposer.propose(state, make_question(n, anchors),
                                            question="zero")
            except RizzoBridgeError as exc:
                record.update(null=True, null_reason=f"engine: {exc}")
            else:
                latency = (time.perf_counter() - t0) * 1000.0
                claim = proposal.model_value
                rep = run_verified("quanto vale lo zero?", ["rapporto"],
                                   calc_kind="zeron", calc_args={"n": n},
                                   precision=PRECISION, model_value=claim)
                record.update(
                    raw_confidence=proposal.confidence,
                    chosen=proposal.value, claim=claim,
                    status=proposal.status, model_id=proposal.model_id,
                    latency_ms=round(latency, 1),
                    outcome=bool(rep.verdict.ok),
                    verdict_code=rep.verdict.code.value)
                valid += 1
                if not rep.verdict.ok:
                    failures += 1

        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        if record["null"]:
            nulls.append(record)

    print(f"\nATTEMPTS={attempts}  VALID={valid}  FAILURES={failures}  "
          f"NULLS={len(nulls)}")
    for fascia in FASCE:
        rows = [json.loads(line) for line in log_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        band = [r for r in rows if not r["null"] and r["fascia"] == fascia]
        if band:
            rate = sum(1 for r in band if r["outcome"]) / len(band)
            print(f"  fascia {fascia}: {len(band)} valide, "
                  f"successo {rate:.2f}")

    if args.pilot:
        return pilot_checks(log_path)
    print(f"LOG={log_path}")
    print("Run terminato. L'analisi (--analyze) si fa ORA, non prima.")
    return 0


def pilot_checks(log_path: Path) -> int:
    """Solo controlli meccanici (doc §9). Nessun AUC, nessun ECE."""
    rows = [json.loads(line) for line in
            log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    valid = [r for r in rows if not r["null"]]

    print("\n== PILOTA: controlli meccanici ==")
    independent = any((r["raw_confidence"] >= 0.8 and not r["outcome"]) or
                      (r["raw_confidence"] <= 0.5 and r["outcome"])
                      for r in valid)
    print(f"1. indipendenza confidenza/esito (§2.3): {independent}")

    rates = {}
    for fascia in FASCE:
        band = [r for r in valid if r["fascia"] == fascia]
        if band:
            rates[fascia] = sum(1 for r in band if r["outcome"]) / len(band)
    differ = len({round(v, 3) for v in rates.values()}) > 1 if rates else False
    print(f"2. tassi per fascia differiscono (§3): {differ}  {rates}")

    required = {"model_id", "vram_free_mib", "latency_ms",
                "selection_probability", "contract_digest", "label_source",
                "fascia", "n"}
    telemetry = all(required <= set(r) for r in valid)
    print(f"3. telemetria completa (§9): {telemetry}")

    ok = independent and differ and telemetry and len(valid) >= 15
    print(f"PILOTA {'SUPERATO: il run puo partire' if ok else 'NON SUPERATO: il run NON parte'}")
    return 0 if ok else 1


# --------------------------------------------------------------------- #
# raccolta logit per il fit di temperatura (RUN4, PREREGISTRAZIONE_RUN4 §2)
# --------------------------------------------------------------------- #

def collect_logits(args: argparse.Namespace) -> int:
    """Righe LabeledLogits dai casi del banco, sull'engine NON calibrato.

    I logit sono deterministici dati i pesi: niente floor VRAM qui (la
    pressione produce errori, non logit diversi); errore engine -> max 3
    tentativi, poi il caso si scarta e si dichiara.
    """
    out_path = Path(args.collect_logits).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = out_path.with_suffix(".meta.jsonl")
    proposer = RizzoProposer(timeout=120.0)
    health = proposer.health()
    model = health.get("model", {})
    print(f"engine: {health.get('status')}  fingerprint={model.get('fingerprint')}")

    rng = random.Random(args.seed)
    truths = {n: kernel_truth(n) for n in ZEROS_N}
    written = skipped = 0

    with out_path.open("w", encoding="utf-8") as fh, \
            meta_path.open("w", encoding="utf-8") as mh:
        for index in range(args.count):
            fascia = FASCE[index % 3]
            n = ZEROS_N[index % len(ZEROS_N)]
            state, anchors, truth = build_case(fascia, n, rng, truths)

            proposal = None
            for _ in range(3):
                try:
                    proposal = proposer.propose(state, make_question(n, anchors),
                                                question="zero")
                    break
                except RizzoBridgeError:
                    time.sleep(2.0)
            if proposal is None:
                print(f"caso {index}: scartato (engine irraggiungibile x3)")
                skipped += 1
                continue

            option_logits = proposal.raw.get("option_logits") or {}
            anchor_ids = [str(i) for i in range(len(anchors))]
            special_ids = [k for k in option_logits if k not in anchor_ids]
            order = anchor_ids + special_ids
            truth_idx = next((i for i, a in enumerate(anchors)
                              if abs(a["value"] - float(truth)) < 1e-9), None)
            if (truth_idx is None or not option_logits
                    or any(k not in option_logits for k in anchor_ids)):
                print(f"caso {index}: scartato (option_logits malformato)")
                skipped += 1
                continue

            row = {"type": "numeric",
                   "logits": [float(option_logits[k]) for k in order],
                   "label_index": truth_idx}
            fh.write(json.dumps(row) + "\n")
            mh.write(json.dumps({"case": index, "fascia": fascia, "n": n,
                                 "truth": truth, "chosen": proposal.value,
                                 "claim": proposal.model_value,
                                 "raw_confidence": proposal.confidence},
                                ensure_ascii=False) + "\n")
            written += 1

    print(f"righe scritte: {written}, scartate: {skipped} -> {out_path}")
    return 0 if written >= 10 else 1


# --------------------------------------------------------------------- #
# analisi (solo dopo la soglia: doc §6)
# --------------------------------------------------------------------- #

def _auc(scores: list[float], outcomes: list[bool]) -> float:
    pos = sorted(s for s, o in zip(scores, outcomes) if o)
    neg = sorted(s for s, o in zip(scores, outcomes) if not o)
    if not pos or not neg:
        return float("nan")
    wins = ties = 0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1
            elif p == q:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def _hm_ci95(auc: float, n_pos: int, n_neg: int) -> tuple[float, float]:
    q1 = auc / (2.0 - auc)
    q2 = 2 * auc * auc / (1.0 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (q1 - auc * auc)
           + (n_neg - 1) * (q2 - auc * auc)) / (n_pos * n_neg)
    half = 1.96 * (var ** 0.5)
    return max(0.0, auc - half), min(1.0, auc + half)


def _ece(scores: list[float], outcomes: list[bool], bins: int = 10) -> float:
    total = len(scores)
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, s in enumerate(scores)
               if lo <= s < hi or (b == bins - 1 and s == 1.0)]
        if idx:
            acc = sum(outcomes[i] for i in idx) / len(idx)
            conf = sum(scores[i] for i in idx) / len(idx)
            ece += len(idx) / total * abs(acc - conf)
    return ece


def analyze(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    log_path = run_dir / f"{run_dir.name}.jsonl"
    rows = [json.loads(line) for line in
            log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    valid = [r for r in rows if not r["null"]]
    failures = sum(1 for r in valid if not r["outcome"])
    print(f"valide={len(valid)}  fallimenti={failures}")
    if len(valid) < 120 or failures < 30:
        print("SOGLIA NON RAGGIUNTA: l'analisi sarebbe esplorativa. Stop.")
        return 1

    scores = [r["raw_confidence"] for r in valid]
    outcomes = [bool(r["outcome"]) for r in valid]
    n_pos, n_neg = sum(outcomes), len(outcomes) - sum(outcomes)

    auc = _auc(scores, outcomes)
    lo, hi = _hm_ci95(auc, n_pos, n_neg)
    ece = _ece(scores, outcomes)

    base_rate = n_pos / len(valid)
    ece_b0 = _ece([base_rate] * len(valid), outcomes)
    rng = random.Random(42)
    auc_b2 = _auc([rng.random() for _ in valid], outcomes)
    b1_hits = sum((s >= 0.9) == o for s, o in zip(scores, outcomes))
    acc_b1 = b1_hits / len(valid)

    report = {
        "n_valid": len(valid), "n_failures": failures,
        "auc": round(auc, 4), "auc_ci95": [round(lo, 4), round(hi, 4)],
        "ece": round(ece, 4),
        "baselines": {"B0_ece": round(ece_b0, 4), "B1_acc_soglia_0.9": round(acc_b1, 4),
                      "B2_auc_random": round(auc_b2, 4)},
        "per_fascia": {f: {"n": sum(1 for r in valid if r["fascia"] == f),
                           "successo": round(sum(1 for r in valid
                                                 if r["fascia"] == f and r["outcome"])
                                             / max(1, sum(1 for r in valid
                                                          if r["fascia"] == f)), 3)}
                       for f in FASCE},
        "affermazione_sostenuta": bool(auc >= 0.70 and lo > 0.5 and ece <= 0.10),
    }
    out = log_path.with_suffix(".analysis.json")
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"REPORT={out}")
    print("Il rapporto si pubblica qualunque sia l'esito (doc §8).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--min-failures", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="riprendi il log esistente senza cancellarlo")
    parser.add_argument("--collect-logits", type=Path, default=None,
                        help="raccoglie LabeledLogits per il fit (RUN4)")
    parser.add_argument("--vram-floor", type=int, default=VRAM_FLOOR_MIB,
                        help="floor MiB; 512 per RUN3 (emendamento 2026-09-21/B)")
    parser.add_argument("--run-dir", default=str(PROJECT_ROOT / "run" / "run2"))
    args = parser.parse_args()
    if args.analyze:
        return analyze(args)
    if args.collect_logits:
        return collect_logits(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
