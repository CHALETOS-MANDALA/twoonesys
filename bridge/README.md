# TWOONESYS / bridge — il punto di contatto

Il ponte fra l'**engine** (Rizzo Flow, System One modello, `:8017`) e
l'**harness** (CASCADE, System One harness). Traduce, non giudica.

## Dove sta il codice

Il modulo del ponte vive dentro il pacchetto dell'harness:
`harness/rizzo_bridge.py` — come `latent_bridge.py`, `eni_brain.py`,
`ollama_router.py`: in CASCADE i proponenti sono moduli del pacchetto.
(Decisione del 2026-09-21: il piano diceva `bridge/rizzo_proposer.py`;
spostato dentro l'harness per seguire l'architettura esistente — import
semplici, test nella suite, storia git unica. Questa cartella resta per i
documenti della fusione e per il runner dei tre proponenti, Fase 4.)

## La mappatura (engine → harness)

| Campo CASCADE | Sorgente engine | Regola |
|---|---|---|
| `raw_confidence` | probabilità del valore scelto, dai logit | segnale vero: mai 0.5 cablato |
| `action_chosen` | il `choice` / `value` | identità del braccio, non il nome del modello (B3) |
| `model_value` | primitiva `numeric`: decimale nudo | claim barrier senza regex sulla prosa |
| `status != "ok"` | `insufficient_evidence` / `out_of_range` / `uncertain` | **astensione mai autorizzata**: il gate resta chiuso, il record dice perché |

## Regole di onestà

- Engine irraggiungibile o risposta malformata → `RizzoBridgeError`.
  Mai un proseguimento di comodo.
- La confidenza è quella dell'engine, **non ricalibrata**: la calibrazione
  sugli esiti osservati resta del `ReliabilityMeter`.
- Nessun numero inventato: astensione → `value=None`, lo status conserva
  il perché.

## Uso

```python
from cascade.rizzo_bridge import RizzoProposer
from cascade.integrated_workflow import IntegratedWorkflow

proposer = RizzoProposer()                      # http://127.0.0.1:8017
proposer.health()                               # engine su? pesi quelli giusti?

wf.run_with_rizzo("req-1", "smista il ticket", docs,
                  proposer,
                  state={"ticket": "addebito errato"},
                  questions={"reparto": {"type": "choice",
                                         "instructions": "Chi gestisce?",
                                         "options": [...]}})
```

Test: `harness/tests/test_rizzo_bridge.py` — 9 test, nessuna rete
(`post_fn` iniettato, come `fake_eni_response` per ENI).
