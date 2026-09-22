# Rapporto RUN2 — calibrazione TWOONESYS engine (1.7B Q8)

Pubblicato come da §8 della pre-registrazione: **qualunque sia l'esito**.
Metodo: `PREREGISTRAZIONE_RUN2_TWOONESYS.md` (congelata, commit c16f872) +
`EMENDAMENTO_RUN2_2026-09-21.md`. Dati: `run/run2/run2.jsonl` (120 record,
0 nulli), analisi in `run2.analysis.json`.

| | |
|---|---|
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine, Spark-X2.5-1.7B Q8, :8017 |
| Oracolo | kernel zeron (n=1..5), claim = ancora scelta dall'engine |
| Decisioni valide | 120 (soglia raggiunta: 120/120, fallimenti 45/30) |

## L'affermazione misurata

> La confidenza dell'engine predice il successo del claim con AUC ≥ 0.70
> ed è calibrata con ECE ≤ 0.10 su 10 bin.

## Esito: NON sostenuta — nelle due metà, separate come la regola impone

| Metà | Risultato | Verdetto |
|---|---|---|
| **Discriminazione** | AUC = **0.739**, IC95 [0.651, 0.826] | **regge**: l'intervallo esclude 0.5; batte B2 (random, 0.506) e B0 (costante, 0.5 per costruzione) |
| **Calibrazione** | ECE = **0.259** | **cade**: oltre il doppio della soglia 0.10 |

La confidenza dell'engine **sa quando ha ragione** (ordina bene i casi) ma
**mente su quanto** (i valori assoluti sono gonfiati).

## Curva di affidabilità (10 bin)

| bin confidenza | n | conf. media | accuratezza reale |
|---|---:|---:|---:|
| [0.3, 0.4] | 4 | 0.392 | 0.000 |
| [0.4, 0.5] | 15 | 0.482 | 0.267 |
| [0.5, 0.6] | 13 | 0.541 | 0.692 |
| [0.7, 0.8] | 8 | 0.757 | 1.000 |
| [0.8, 0.9] | 15 | 0.841 | 0.467 |
| [0.9, 1.0] | 65 | **0.981** | **0.723** |

Il 54% delle decisioni si ammassa nel bin più alto: l'engine dice «98%» e
azzecca il 72%. Sovra-confidenza da modello piccolo, esattamente il fenomeno
che il cancello esiste per governare.

## Le baseline (dichiarate prima)

- **B0** (costante al tasso base 0.625): ECE = 0.000, AUC = 0.5. *Perfettamente
  calibrata e inutile* — la trappola che la pre-registrazione aveva previsto,
  qui dimostrata su dati veri.
- **B1** (soglia fissa 0.9 sulla grezza): accuratezza 0.617, peggio del tasso
  base. La soglia fissa non aggiunge nulla.
- **B2** (confidenza casuale): AUC 0.506. Il segnale dell'engine non è rumore.

## Fasce (la stratificazione ha funzionato)

| Fascia | n | successo | atteso |
|---|---:|---:|---:|
| A — facile | 40 | 1.00 | ~0.95 |
| B — media | 40 | 0.55 | ~0.75 |
| C — difficile (evidenza mancante) | 40 | 0.33 | ~0.50 |

B e C più dure del previsto per l'1.7B: la trappola «stima preliminare
superata» (B) e l'evidenza assente (C) mietono fallimenti — varianza vera,
che è ciò che il banco deve produrre.

## Cosa significa per TWOONESYS

1. **Il segnale c'è** (AUC 0.74 con IC che esclude il caso): la confidenza
   dell'engine è una *misura*, non un'etichetta.
2. **La calibrazione non è opzionale**: con ECE 0.26, la confidenza grezza
   non può essere presa alla lettera. Il ReliabilityMeter del harness è il
   componente che trasforma questo segnale in probabilità oneste — RUN2 è la
   sua prima giustificazione misurata, non argomentata.
3. **Passo successivo dichiarato**: ricalibrazione split-half su questi dati
   (esplorativa, etichettata come tale), poi RUN3 con il 4B quando il disco
   lo permette — stesso contratto, stesso banco, `model_id` diverso = dataset
   separato (regola §7).

*Analisi eseguita solo dopo la soglia (120/30), come da regola di arresto.*
