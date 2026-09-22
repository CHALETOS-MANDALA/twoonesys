# Rapporto RUN5 — la calibrazione è componibile: SÌ (fuori campione)

Pubblicato come da regola. Metodo: `PREREGISTRAZIONE_RUN5_TWOONESYS.md`
(congelata prima del fit). Base esplorativa dichiarata: `reverse_calibration.py`
(in-sample). Valutazione appaiata con RUN4: stessa popolazione (seed 2026),
stessi esiti (argmax invariante), diversa mappa di calibrazione.
Dati: `run/run5_eval/eval_logits.jsonl`, analisi in `run5.analysis.json`.

| | |
|---|---|
| Data | 2026-09-21 |
| Proponente | 4B Q8, logit crudi + temperatura per condizione applicata dal harness |

## Esito: SOSTENUTA

| mappa | AUC | ECE | |
|---|---:|---:|---|
| **condizionata** | **1.000** [1.000, 1.000] | **0.069** | ✅ entrambe le soglie |
| globale (RUN4) | 0.691 [0.596, 0.787] | 0.182 | riprodotta esatta (controllo di coerenza) |
| nulla (grezza) | 0.663 [0.564, 0.761] | 0.294 | |

Temperature fittate (griglia estesa [0.01, 100]): **A: 0.01, B: 0.01, C: 100**
— tutte ai bordi: conta la direzione. *Affila* dove l'evidenza c'è, *demolisci*
dove manca.

## Il reverse engineering della calibrazione, in una frase

T=3.947 (RUN4) era la media di due verità opposte — «il modello è
sotto-confidente quando l'evidenza c'è» e «è catastroficamente sovra-confidente
quando manca» — e non ne soddisfaceva nessuna. Scomposta per condizione, la
calibrazione chiude: **l'errore viveva nella struttura, non nel modello.**

## Limiti dichiarati (parte del risultato, non una nota a piè)

1. **La condizione qui è data dal banco** (fascia A/B/C, nota pre-decisione
   per costruzione). In produzione la condizione «evidenza presente/assente»
   va *rilevata*: è esattamente il territorio del detector di PCT e
   dei suoi due campi (scala dei costi + ordine temporale). RUN5 dimostra che
   *se la condizione è nota* la calibrazione chiude; la rilevazione della
   condizione è il cantiere aperto.
2. **AUC 1.0 riflette la struttura pulita del banco** (su seed 2026: A e B
   tutte riuscite, C tutte fallite — la condizione determina l'esito).
   Condizioni reali separeranno meno nettamente.
3. T ai bordi della griglia: i valori esatti sono oltre la griglia; le
   direzioni sono il contenuto.

## La catena, chiusa

1. Segnale: la confidenza discrimina (RUN2/3). ✅
2. Misura onesta: metodo congelato, esiti pubblicati anche perdenti. ✅
3. Calibrazione aggregata: aiuta, non basta (RUN4). ✅
4. **Calibrazione condizionata: chiude, fuori campione (RUN5).** ✅
5. Produzione: rilevare la condizione sui log reali — PCT, i due campi,
   e il detector. ⬅️ il prossimo cantiere

*Seed fit 42, seed valutazione 2026, nessuna sovrapposizione di istanze.*
