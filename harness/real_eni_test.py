"""TEST VERO: ENI reale -> CASCADE pipeline (causale + guard Z3).

Collega il cervello standalone ENI (localhost:8001) al pipeline CASCADE e
esegue una decisione di controllo completa. Nessuna simulazione: la confidenza
e la proposta arrivano da ENI su Ollama.

Uso:
    python cascade/real_eni_test.py [--action 4.0] [--noise]
"""

import argparse
import asyncio
import os
import sys

# il package cascade puo' stare ovunque: aggiungi la cartella del progetto
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)  # parent di cascade/
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from cascade.contracts import Task
    from cascade.eni_brain import ENIBrain
    from cascade.neurosymbolic_guard import ConfidenceLevel
    from cascade.pipeline import CascadePipeline, PipelineConfig
except ImportError as exc:
    print(f"Impossibile importare CASCADE: {exc}")
    print(f"Cercato in: {_PROJECT_ROOT}")
    sys.exit(1)


def build_problem(state, action, noise: bool) -> str:
    return (
        "Sistema di controllo di un oscillatore. Stato attuale: "
        f"posizione {state[0]}, velocita' {state[1]}. "
        f"Rumore esterno: {'presente' if noise else 'assente'}. "
        "L'agente propone un'azione di correzione forte "
        f"{action}. "
        "Decidi quale azione di controllo sicura consigliare e con quale "
        "confidenza, valutando il rischio."
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", type=float, default=4.0, help="azione proposta")
    ap.add_argument("--noise", action="store_true", help="rumore esterno attivo")
    ap.add_argument("--pos", type=float, default=0.5)
    ap.add_argument("--vel", type=float, default=0.3)
    ap.add_argument("--threshold", type=float, default=None,
                    help="soglia confidenza (default: EXPLORATORY=0.8). "
                         "Es. --threshold 0.5 per vedere l'autorizzazione.")
    args = ap.parse_args()
    state = [args.pos, args.vel]

    threshold = (
        args.threshold
        if args.threshold is not None
        else ConfidenceLevel.EXPLORATORY.value
    )
    print("=" * 60)
    print("TEST VERO: ENI (reale) -> CASCADE (causale + guard Z3)")
    print(f"soglia confidenza: {threshold}")
    print("=" * 60)

    # 1) ENI reale propone
    brain = ENIBrain()
    problem = build_problem(state, args.action, args.noise)
    print(f"\n[1] Interrogo ENI reale ({problem[:80]}...)")
    try:
        sig = await brain.propose(problem, default_action=args.action)
    except Exception as exc:  # noqa: BLE001
        print(f"    ERRORE: ENI non raggiungibile: {exc}")
        print("    Il guard Z3 di CASCADE non puo' verificare nulla -> sicurezza.")
        return
    print(f"    ENI risponde -> azione: {sig.proposal['action']}, "
          f"confidenza REALE: {sig.confidence:.3f}")

    # 2) CASCADE verifica
    pipe = CascadePipeline(PipelineConfig(confidence_threshold=threshold))
    man = brain.manifest()
    pipe.register_agent(man)

    task = Task("real_test", "controllo", {}, max_cost=1.0)
    dec = pipe.run(task, [sig], state=state, noise=args.noise)

    print(f"\n[2] CASCADE valuta:")
    print(f"    agente:          {dec.agent_id}")
    print(f"    approvato:       {dec.approved}")
    print(f"    certificato:     {dec.certified}")
    print(f"    output finale:   {dec.final_output}")
    if dec.evidence:
        p_inc = dec.evidence.posteriors.get("P(incidente)", {})
        print(f"    P(incidente):    {p_inc}")
        print(f"    controfattuali:  {dec.evidence.counterfactuals}")
    else:
        print("    (nessuna evidenza causale: bloccato prima)")
    if dec.violations:
        print(f"    violazioni:      {dec.violations}")
    if dec.forecast:
        print(f"    previsione stato: {dec.forecast.predicted_next_state}, "
              f"stabile: {dec.forecast.stable}")

    print("\n" + "=" * 60)
    if dec.approved:
        print("ESITO: AUTORIZZATO E CERTIFICATO")
    else:
        print("ESITO: BLOCCATO/MITIGATO DALLA CATENA DI SICUREZZA")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
