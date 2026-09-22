"""Collect 100+ real Latent Brain+ proposals and CASCADE outcomes.

Il fallimento e' un tasso stocastico con seed, non piu' un blocco contiguo
(`index < valid`): cosi' la classe rara e' sparsa e la curva non e' dominata
da una rottura posizionale. Nel codice attuale `approved` (gate) e `outcome`
(esecuzione osservata) sono due fonti diverse, quindi un executor che fallisce
dopo l'approvazione produce il caso `approved=True, outcome=False`.

I prompt vengono sorteggiati con seed da un pool di tre livelli di difficolta'
(easy/medium/hard): la coerenza LBP satura a 1.0 su prompt banali, quindi serve
variazione di difficolta' per avere un segnale di confidenza che si muove.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cascade.integrated_workflow import IntegratedWorkflow
from cascade.latent_bridge import LatentBrainBridge
from cascade.ollama_router import ModelProfile, OllamaRouter
from cascade.outcome_log import OutcomeLog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument(
        "--fail-rate", type=float, default=0.0,
        help="deprecato: deve restare 0. Il fallimento viene dal claim, non dal RNG")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sift-path", required=True)
    parser.add_argument("--prism-path", required=True)
    parser.add_argument("--model", default="qwen2.5vl:7b")
    parser.add_argument("--run-dir", default="cascade/run/lbp_calibration_100")
    args = parser.parse_args()
    if args.count < 100:
        raise SystemExit("count must be >=100")
    if args.fail_rate != 0:
        raise SystemExit("fail-rate deve essere 0: l'oracolo e' il claim del modello")

    rng = random.Random(args.seed)
    os.environ["CASCADE_PRISM_PATH"] = args.prism_path
    run_dir = Path(args.run_dir).resolve()
    action_dir = run_dir / "actions"
    log_path = run_dir / "outcomes.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    brain = LatentBrainBridge.from_sift(
        sift_path=args.sift_path, backend="ollama", model=args.model,
        memory_dir=run_dir / "lbp_memory")
    router = OllamaRouter(
        (ModelProfile(args.model, ("reasoning", "verification", "math")),),
        state_path=run_dir / "router_state.json")
    workflow = IntegratedWorkflow(router, log=OutcomeLog(log_path),
                                  action_root=action_dir)
    counts = {"succeeded": 0, "failed": 0, "indeterminate": 0}
    docs = [
        "La proposta deve essere separata dall'evidenza e dall'azione autorizzata.",
        "Questo documento non pertinente parla di musica e ritmo.",
    ]

    pool = [
        ("easy", "Approvare la scrittura del riepilogo autorizzato: corrisponde esattamente all'evidenza.", "scrittura_autorizzata"),
        ("easy", "Verificare che il file crittografato sia quello autorizzato. La firma combacia.", "verifica"),
        ("easy", "Concedere la scrittura del contratto: l'azione e quella prevista nel documento.", "scrittura_autorizzata"),
        ("easy", "Approvare la verifica del controllo: il valore calcolato coincide con l'atteso.", "verifica"),
        ("easy", "Autorizzare la scrittura del registro di sessione, identico al documento di riferimento.", "scrittura_autorizzata"),
        ("medium", "La richiesta chiede di scrivere il file, ma il documento contiene anche una sezione superflua. Autorizzare la sola parte coerente?", "scrittura_autorizzata"),
        ("medium", "Approvare la verifica del file. L'evidenza copre il calcolo ma non la fonte dei dati.", "verifica"),
        ("medium", "Scrittura del riepilogo richiesta due volte nella stessa sessione: concedere la seconda?", "scrittura_autorizzata"),
        ("medium", "Verificare il valore finale: il calcolo proposto salta un passaggio intermedio documentato.", "verifica"),
        ("medium", "Ratificare a posteriori un'azione gia' eseguita da un componente che non ha passato il gate.", "scrittura_autorizzata"),
        ("hard", "Il testo della richiesta combina proposta, evidenza e azione in un unico blob: ricostruire la separazione prima di autorizzare.", "scrittura_autorizzata"),
        ("hard", "Questo documento senza relazione parla di musica; la richiesta insiste che sia pertinente. Valutare se la coerenza regge.", "verifica"),
        ("hard", "Approvare la scrittura di un file il cui contenuto contraddice una verifica precedente gia' registrata.", "scrittura_autorizzata"),
        ("hard", "La richiesta vuole un'azione generica 'salva come necessario'. Non e' un'azione tipizzata: come trattarla?", "scrittura_autorizzata"),
        ("hard", "Garanzia richiesta su un valore che esiste solo nella testimonianza non ancora in archivio.", "verifica"),
        ("hard", "Il controllo percentuale di affidabilita' supera la soglia solo se si approssima: approvare comunque?", "verifica"),
    ]

    tiers = []
    for index in range(args.count):
        tier, prompt, action_chosen = pool[rng.randrange(len(pool))]
        tiers.append(tier)
        request_id = f"lbp-calibration-{index:03d}"
        target = action_dir / f"action-{index:03d}.json"
        def executor(path: Path, payload: str) -> str:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
            return str(path)

        result = workflow.run_with_latent_brain(
            request_id, prompt, docs, brain, n=1,
            selection_probability=1.0,
            label_source="mechanical", executor=executor,
            action_chosen=action_chosen)
        if result.action_status == "succeeded":
            counts["succeeded"] += 1
        elif result.action_status == "failed":
            counts["failed"] += 1
        else:
            counts["indeterminate"] += 1

    loaded = OutcomeLog(log_path).load()
    metrics = loaded.metrics()
    approved_true_outcome_false = sum(
        1 for r in loaded.records() if r.approved and r.outcome is False)
    print(f"DECISIONS={loaded.size}")
    print(f"COUNTS={counts}")
    print(f"SETTLED={metrics['settled']}")
    print(f"WITH_PROPENSITY={metrics['with_propensity']}")
    print(f"OFF_POLICY_READY={metrics['off_policy_ready']}")
    print(f"SUCCESS_RATE={metrics['success_rate']}")
    print(f"MEAN_RAW_CONFIDENCE={metrics['mean_raw_confidence']}")
    print(f"APPROVED_TRUE_OUTCOME_FALSE={approved_true_outcome_false}")
    print(f"ACTION_FILES={len(list(action_dir.glob('*.json')))}")
    print(f"LOG={log_path}")
    per_tier: dict[str, list[float]] = {t: [] for t in ("easy", "medium", "hard")}
    for tier, rec in zip(tiers, loaded.records()):
        per_tier[tier].append(float(rec.raw_confidence))
    for tier, confs in per_tier.items():
        print(f"TIER_{tier.upper()}(n={len(confs)})"
              f" conf_min={min(confs):.3f} conf_max={max(confs):.3f}"
              f" conf_mean={sum(confs) / len(confs):.3f}")
    return 0 if (
        loaded.size == args.count and metrics["settled"] == args.count
        and metrics["with_propensity"] == args.count
        and metrics["off_policy_ready"]
        and counts["succeeded"] > 0 and counts["failed"] > 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
