# Rapporto — test nel mondo reale (2026-09-21)

Fuori dal laboratorio Riemann. Ticket in italiano, ledger strutturale,
M4 soft, policy, mondo osservato sul disco, ricevute firmate.

Script: `bridge/real_world_run.py`  
Log: `bridge/run_real/outcomes.jsonl`  
Sandbox: `bridge/sandbox_real/`  
Ricevute: `bridge/receipts_real/`

## Cosa è successo

| caso | raw | M4 testuale | M4 strutturale | auth | mondo |
|---|---:|---:|---:|---|---|
| T-1001 rimborso, ledger OK | 1.000 | 1.000 | 1.000 | sì | sì |
| **T-1001 STESSO testo, ledger VUOTO** | 1.000 | **1.000** | **0.537** | sì | sì |
| T-1002 bug app, no evidenza | 0.946 | 0.584 | 0.509 | sì | sì |
| T-1003 sales, no evidenza | 0.999 | 0.999 | 0.524 | sì | sì |
| path fuori sandbox | 1.000 | — | — | **no** | file non creato |

## La tesi, sul mondo

1. **Divergenza reale (caso 2):** il cliente parla di screenshot; il testuale
   resta a 1.0; la struttura (ledger vuoto) porta M4 a 0.54. Stesso ticket,
   stessa decisione `billing`, unica variabile = fatti di sistema.
2. **Policy indipendente:** anche con raw_p=1.0 la scrittura fuori sandbox
   è rifiutata e la ricevuta di deny verifica.
3. **Mondo osservato:** `outcome` letto dal file sul disco, non dal ritorno
   dell’executor. Campi `outcome_contract` + fasi dichiarate (verso PCT).

Non è un run statistico (n=4). È la prova che la filiera gira sul reale:
engine → detector strutturale → M4 → policy → disco → ricevuta.
