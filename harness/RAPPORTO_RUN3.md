# Rapporto RUN3 — calibrazione TWOONESYS engine (4B Q8)

Pubblicato come da §8: **qualunque sia l'esito**. Metodo:
`PREREGISTRAZIONE_RUN2_TWOONESYS.md` (c16f872) + emendamenti 2026-09-21
(anchor crescenti), 2026-09-21/RUN3 (floor 1024), 2026-09-21/B (floor 512,
fix arresto anticipato, resume). Dataset separato da RUN2 per cambio
`model_id` (regola §7). Dati: `run/run3/run3.jsonl` (120 valide, 49
fallimenti, nulli conservati con motivo), analisi in `run3.analysis.json`.

| | |
|---|---|
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine, Spark-X2.5-**4B** Q8, :8017 |
| Oracolo | kernel zeron (n=1..5), claim = ancora scelta dall'engine |

## Esito: NON sostenuta — con la stessa struttura di RUN2, più nitida

| Metà | Risultato | Verdetto |
|---|---|---|
| **Discriminazione** | AUC = **0.775**, IC95 [0.693, 0.857] | **regge**: esclude 0.5, sopra B2 (0.605) |
| **Calibrazione** | ECE = **0.282** | **cade**: oltre la soglia 0.10 |

## Il confronto che conta: 1.7B vs 4B, stesso contratto

| | RUN2 (1.7B) | RUN3 (4B) | Lettura |
|---|---:|---:|---|
| AUC | 0.739 [0.651, 0.826] | 0.775 [0.693, 0.857] | la scala migliora la discriminazione (poco) |
| ECE | 0.259 | 0.282 | la scala **non** migliora la calibrazione |
| Fascia A (facile) | 1.00 | 1.00 | saturo |
| Fascia B (distrattore) | 0.55 | 0.78 | il 4B legge meglio |
| Fascia C (evidenza mancante) | 0.33 | **0.00** | il 4B cade *sempre* nella trappola |

La scoperta del run: **il modello più grande è più accurato ma non più
onesto.** In fascia C — dove il rapporto dichiara il dato mancante e
`allow_abstain=false` forza la scelta — il 4B sceglie sistematicamente il
valore-trappola riportato per l'`n` sbagliato, e lo fa con confidenza alta.

## Curva di affidabilità (10 bin)

| bin confidenza | n | conf. media | accuratezza reale |
|---|---:|---:|---:|
| [0.3, 0.4] | 6 | 0.341 | 0.000 |
| [0.4, 0.5] | 3 | 0.414 | 0.000 |
| [0.7, 0.8] | 16 | 0.752 | 0.500 |
| [0.8, 0.9] | 20 | 0.854 | 0.600 |
| [0.9, 1.0] | 75 | **0.966** | **0.680** |

Il 62% delle decisioni nel bin più alto: dice «97%», azzecca il 68%.

## Baseline (dichiarate prima)

- **B0** (costante al tasso base): ECE = 0.000, AUC = 0.5 — calibrata e inutile.
- **B1** (soglia fissa 0.9): accuratezza 0.633 — la soglia fissa non basta.
- **B2** (confidenza casuale): AUC 0.605 — rumore con code; il segnale vero
  resta distante (IC95 [0.693, 0.857]).

## Cosa significa per TWOONESYS

1. **La tesi del cancello esce rafforzata**: due modelli, due scale, stesso
   difetto — la confidenza grezza discrimina ma mente in valore assoluto.
   La ricalibrazione sugli esiti osservati (ReliabilityMeter / `rizzo
   calibrate`) è il componente decisivo, ora con due misure a sostegno.
2. **La fascia C è il prodotto**: «cosa fa il sistema quando l'evidenza
   manca» è la domanda che nessun benchmark di accuratezza pone. Qui ha un
   numero: 0/40 col 4B, e la confidenza non lo segnala abbastanza (AUC 0.78,
   non 1.0). Un cancello che sa *di non sapere* quando manca l'evidenza vale
   più di un modello più grande.
3. **Passo successivo dichiarato**: RUN4 — stesso contratto, engine servito
   con `--calibration` fittata sui dati RUN2+RUN3 (split: fit su una metà,
   valutazione sull'altra, mai sul tutto). Se l'ECE scende sotto 0.10
   fuori campione, la catena è chiusa: segnale → misura → calibrazione →
   confidenza onesta.

*Analisi eseguita solo dopo la soglia (120/49), come da regola di arresto.*
