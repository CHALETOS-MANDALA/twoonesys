"""Run the live CASCADE workflow against Ollama, PRISM, and KIARNEL."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cascade.integrated_workflow import IntegratedWorkflow
from cascade.ollama_router import ModelProfile, OllamaRouter
from cascade.outcome_log import OutcomeLog


CHAT_SYSTEM = (
    "Sei CASCADE, un assistente locale gestito da un harness verificabile. "
    "Rispondi in italiano, in modo diretto e conciso. "
    "Non inventare identita' o fatti: se non sai qualcosa, dichiaralo. "
    "CASCADE coordina modelli, PRISM e KIARNEL; non dire di essere un chatbot generico. "
    "Nel progetto dell'utente, Latent Brain+ e' il livello cognitivo: memoria, "
    "contesto e ragionamento assistito. CASCADE e' l'harness e il controllore "
    "operativo che seleziona modelli, verifica evidenza e autorizza azioni. "
    "PRISM seleziona la pertinenza dell'evidenza. KIARNEL esegue calcoli "
    "deterministici verificabili. Non descrivere Latent Brain+ come un modello "
    "sconosciuto senza prima usare questa definizione."
)


def visible_answer(text: str) -> str:
    """Hide private reasoning markers from the interactive transcript."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--chat", action="store_true",
                        help="start an interactive chat session")
    parser.add_argument("--model", default="deepseek-r1:7b")
    parser.add_argument("--request-id", default="manual-live-run")
    parser.add_argument("--run-dir", default="cascade/run")
    parser.add_argument("--prism-path", default=os.environ.get("CASCADE_PRISM_PATH", ""))
    args = parser.parse_args()

    if not args.prism_path:
        raise SystemExit("PRISM path missing: use --prism-path or CASCADE_PRISM_PATH")
    if not args.chat and not args.prompt:
        raise SystemExit("provide a prompt or use --chat")
    os.environ["CASCADE_PRISM_PATH"] = args.prism_path

    run_dir = Path(args.run_dir)
    log_path = run_dir / "manual_live_run.jsonl"
    router = OllamaRouter(
        (ModelProfile(args.model, ("reasoning", "verification", "math")),),
        state_path=run_dir / "manual_router_state.json",
    )
    if args.chat:
        return chat(router)

    workflow = IntegratedWorkflow(
        router, log=OutcomeLog(log_path), action_root=run_dir / "manual_actions")
    result = workflow.run(
        args.request_id,
        args.prompt,
        [
            "A verified chain separates model proposal, deterministic evidence, and authorized action.",
            "This unrelated document discusses music and rhythm.",
        ],
        n=1,
    )
    print(f"MODEL_STATUS={result.generation.status}")
    print(f"MODEL={result.generation.model}")
    print(f"ATTEMPTS={result.generation.attempts}")
    print(f"EVIDENCE_OK={result.evidence.verdict.ok}")
    print(f"STAGES={[(stage.worker, stage.status.value) for stage in result.evidence.stages]}")
    print(f"ACTION_STATUS={result.action_status}")
    print(f"ACTION_RECEIPT={result.action_receipt}")
    print(f"LOG={log_path.resolve()}")
    print(f"ACTION={(run_dir / 'manual_actions' / f'{args.request_id}.json').resolve()}")
    return 0 if result.action_status == "succeeded" else 1


def chat(router: OllamaRouter) -> int:
    history: list[str] = []
    print(f"CASCADE chat attiva. Modello: {next(iter(router.profiles))}")
    print("Scrivi /exit per uscire, /clear per cancellare lo storico.")
    while True:
        try:
            message = input("tu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if message == "/exit":
            return 0
        if message == "/clear":
            history.clear()
            print("storico cancellato")
            continue
        if not message:
            continue
        history.append(f"Utente: {message}")
        prompt = (
            "Sei in una conversazione. Rispondi direttamente all'ultimo messaggio.\n"
            + "\n".join(history)
            + "\nAssistente:"
        )
        result = router.generate(prompt, system=CHAT_SYSTEM, num_predict=512)
        if result.status != "succeeded":
            print(f"cascade> errore modello: {result.error}")
            history.pop()
            continue
        answer = visible_answer(result.text)
        if not answer:
            print("cascade> il modello non ha prodotto una risposta visibile")
            history.pop()
            continue
        history.append(f"Assistente: {answer}")
        print(f"cascade> {answer}")


if __name__ == "__main__":
    raise SystemExit(main())