# Rapporto RUN8 — detector strutturale vs M4-soft testuale

Pubblicato come da regola. Metodo: `PREREGISTRAZIONE_RUN8_DETECTOR.md` +
`EMENDAMENTO_RUN8_TOLLERANZE_2026-09-21.md`. Variabile unica: il detector.
Stesso M4 soft (T_presente=0.01, T_absent=100), stessi casi appaiati.

## Verdetto: **H1 sostenuta** (H0 rifiutata)

| Condizione congelata | Esito |
|---|---|
| Lab: ECE≤0.10, AUC≥0.70, ΔECE vs M4-testuale ≤0.0287 | **OK** — strutt ECE 0.0698, AUC 1.0, Δ=−0.0015 |
| OOD: IC95 bootstrap (ECE_test − ECE_strutt) esclude 0 | **OK** — diff 0.2508, IC95 **[0.153, 0.342]** |
| OOD: ECE_strutt ≤ ECE_test | **OK** — 0.655 ≤ 0.906 |

## Laboratorio (seed 2026, n=120)

| detector | ECE | AUC | Brier | NLL |
|---|---:|---:|---:|---:|
| testuale (baseline M4) | 0.0713 | 1.000 | — | — |
| **strutturale** | **0.0698** | **1.000** | 0.0146 | 0.0783 |

Il laboratorio si preserva; lo strutturale è anzi leggermente meglio.

## OOD (n=96, 12×D1..D8, 0 nulli)

| detector | ECE | Brier | NLL | AUROC detector |
|---|---:|---:|---:|---:|
| testuale | **0.906** | 0.883 | 24.19 | 0.00 (invertito: il testo mente) |
| **strutturale** | **0.655** | 0.533 | 5.46 | **1.00** |

Confusion (s>0): strutturale tp=12 tn=84 fp=0 fn=0; testuale tp=0 tn=0 fp=84 fn=12.

**AUC confidence = NaN** su OOD: sotto la definizione operativa di outcome
usata qui, tutti i 96 casi hanno `outcome=False` (nessun successo). La
discriminazione della confidence non è misurabile su questo sotto-banco;
la primaria congelata resta l’**ECE** (e il bootstrap), non l’AUC.

## Per tipo (ECE) — dove guadagna e dove no

| tipo | ECE testuale | ECE strutt | nota |
|---|---:|---:|---|
| D1 testo dice esiste / strutt assenza | 1.000 | **0.350** | strutt smonta la confidenza |
| D2 testo dice manca / strutt verifica | **0.246** | 1.000 | **strutt peggiora**: affila su testo bugiardo |
| D3 incompleta | 1.000 | 0.943 | lieve |
| D4 stale | 1.000 | 0.998 | ~pari |
| D5 verifica fallita | 1.000 | **0.818** | guadagno |
| D6 conflitto fonti | 1.000 | **0.651** | guadagno |
| D7 status unknown | 1.000 | **0.237** | guadagno forte |
| D8 irraggiungibile | 1.000 | **0.243** | guadagno forte |

## Lettura onesta

1. **H1 regge** sui criteri scritti prima: lab intatto, ECE OOD migliore
   con IC che esclude 0.
2. Il detector strutturale **legge i fatti** (AUROC 1.0 sul label di
   evidenza); il testuale sull’OOD è sistematicamente invertito.
3. **D2 è il prezzo:** quando la struttura dice «evidenza c’è» ma il testo
   mente e il modello sbaglia comunque il claim, M4 soft *affila* una
   confidenza alta sul fallimento. Aggregato vince; sul tipo D2 no.
4. Outcome OOD tutto-negativo limita ciò che si può dire sulla
   discriminazione della confidence: prossimo emendamento potrà definire
   outcome D2 in modo che i claim corretti contino come successi senza
   toccare H0/H1 già giudicate su ECE.

## Artefatti

- `detector_contract.py` — fatti tipizzati + score
- `ood_cases.py` — banco D1–D8 validato meccanicamente
- `run8_eval.py` — eval appaiato
- `run/run8/ood_bank.jsonl`, `ood_records.jsonl`, `run8.analysis.json`
