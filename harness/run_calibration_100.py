"""Collect 100+ real System One outcomes with recorded action propensity.

Ground truth INDIPENDENTE dall'approvazione: l'`outcome` non viene dal ritorno
dell'executor ma dalla RILETTURA DEL MONDO dopo l'azione (il file esiste e il
suo contenuto combacia col request_id). Cosi' nasce il caso che la verifica
indipendente chiedeva: `approved=True, outcome=False` — il gate ha eseguito e
l'esecutore ha detto ok, ma il mondo dice che l'effetto non c'e' stato.

Il fallimento non e' piu' un blocco contiguo (`index < valid`): e' un tasso
stocastico con seed, cosi' i fallimenti sono sparsi e la classe rara esiste
davvero in modo indipendente dalla posizione.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cascade.action_authorize import GrantRegistry, grant_from_permit
from cascade.contracts_v1 import Permit, Succeeded, contract_digest
from cascade.outcome_log import OutcomeLog
from cascade.system_one import SystemOneLoop


def issue(request_id: str, params: dict[str, str]):
    permit = Permit(
        action_digest=contract_digest(action="file_write", scope="fs.write"),
        arguments_digest=contract_digest(**params),
        scope=("fs.write",), preconditions=(), expires_at=4_000_000_000,
        grant_id=request_id, subject_id="calibration-operator")
    grant = grant_from_permit(
        permit, tool="file_write", scope="fs.write", params=params,
        request_id=request_id, operation_id=request_id)
    registry = GrantRegistry()
    registry.issue(grant)
    return registry, permit, grant


def _world_observes(target: Path, request_id: str) -> bool:
    """Ground truth: rilegge il MONDO, non si fida del ritorno dell'executor."""
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload.get("request_id") == request_id and target.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--fail-rate", type=float, default=0.15,
                        help="frazione di esecuzioni che falliscono (seed)")
    parser.add_argument("--drop-rate", type=float, default=0.10,
                        help="frazione di scritture silenziosamente perse: "
                             "l'executor dice ok ma il mondo non vede l'effetto "
                             "(approved=True, outcome=False)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-dir", default="cascade/run/calibration_100")
    args = parser.parse_args()
    if args.count < 100:
        raise SystemExit("count must be >=100")
    if not (0 <= args.fail_rate < 1) or not (0 <= args.drop_rate < 1):
        raise SystemExit("fail-rate and drop-rate must be in [0,1)")

    rng = random.Random(args.seed)
    run_dir = Path(args.run_dir).resolve()
    action_dir = run_dir / "actions"
    log_path = run_dir / "outcomes.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()
    log = OutcomeLog(log_path)
    loop = SystemOneLoop(log=log)
    counts = {"succeeded": 0, "failed": 0, "indeterminate": 0,
              "world_disagrees": 0}

    for index in range(args.count):
        request_id = f"calibration-{index:03d}"
        target = action_dir / f"action-{index:03d}.json"
        params = {"path": str(target)}
        registry, permit, grant = issue(request_id, params)
        selection_probability = 0.25 if index % 4 == 0 else 0.75
        roll = rng.random()
        hard_fail = roll < args.fail_rate
        silent_drop = (not hard_fail) and (roll < args.fail_rate + args.drop_rate)

        def executor(p: dict[str, str], *, _hard=hard_fail,
                     _drop=silent_drop) -> dict:
            if _hard:
                raise OSError("real executor failure: target unavailable")
            if _drop:
                return {"ok": True, "path": p["path"], "dropped": True}
            t = Path(p["path"])
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(json.dumps({"request_id": request_id,
                                     "source": "real-filesystem"}),
                         encoding="utf-8")
            return {"ok": True, "path": str(t), "bytes": t.stat().st_size}

        a = loop.assess(request_id, "file_write", 0.5 + (index % 50) / 100)
        result, _ = loop.dispose(
            a, registry=registry, permit=permit, grant_doc=grant.to_dict(),
            tool="file_write", scope="fs.write", params=params, state=params,
            executor=executor, system_two=lambda: True)
        # ground truth: si legge il MONDO DOPO l'esecuzione, mai il ritorno
        loop.settle(a, result, outcome=_world_observes(target, request_id),
                    action_chosen="file_write",
                    selection_probability=selection_probability,
                    contract_digest="system-one-file-write-v3",
                    label_source="mechanical")
        rec = log.records()[-1]
        if isinstance(result, Succeeded):
            counts["succeeded"] += 1
        elif result.__class__.__name__ == "Indeterminate":
            counts["indeterminate"] += 1
        else:
            counts["failed"] += 1
        if rec.approved and not rec.outcome:
            counts["world_disagrees"] += 1

    loaded = OutcomeLog(log_path).load()
    metrics = loaded.metrics()
    approved_true_outcome_false = sum(
        1 for r in loaded.records() if r.approved and r.outcome is False)
    approved_false = sum(1 for r in loaded.records() if not r.approved)
    print(f"DECISIONS={loaded.size}")
    print(f"COUNTS={counts}")
    print(f"SETTLED={metrics['settled']}")
    print(f"WITH_PROPENSITY={metrics['with_propensity']}")
    print(f"OFF_POLICY_READY={metrics['off_policy_ready']}")
    print(f"SUCCESS_RATE={metrics['success_rate']}")
    print(f"APPROVED_TRUE_OUTCOME_FALSE={approved_true_outcome_false}")
    print(f"APPROVED_FALSE={approved_false}")
    print(f"ACTION_FILES={len(list(action_dir.glob('*.json')))}")
    print(f"LOG={log_path}")
    if loaded.size != args.count or metrics["settled"] != args.count:
        return 1
    if metrics["with_propensity"] != args.count or not metrics["off_policy_ready"]:
        return 1
    if counts["succeeded"] == 0 or counts["failed"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
