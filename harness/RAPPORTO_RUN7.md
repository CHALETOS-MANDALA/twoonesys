# Rapporto RUN7 — migliorare la sopravvivenza: Pareto, non vittoria netta

Pubblicato come da regola. Metodo: `PREREGISTRAZIONE_RUN7_TWOONESYS.md`.
Sola lettura. Controllo M0: OK (riproduce RUN6).

## Affermazione §1: **NON sostenuta**

Nessuna mappa ha soddisfatto *entrambi* i vincoli (pulito ECE≤0.10 ∧ AUC≥0.70
**e** a ε=0.20: ECE≤0.10-o-migliore-di-M0 ∧ AUC≥0.85).

Questo non è un fallimento del metodo: è la misura del trade-off.

## Pareto (i numeri che contano)

| mappa | ECE pulito | AUC pulito | ECE ε=0.20 | AUC ε=0.20 | note |
|---|---:|---:|---:|---:|---|
| **M0** dura RUN6 | **0.069** ✅ | 1.000 | 0.103 ❌ | 0.837 | baseline |
| M1 T regolarizzata λ=0.05 | 0.161 ❌ | 1.000 | **0.085** | **0.854** | robusta sotto flip, **rompe il laboratorio** |
| M2 T vincolata [0.2,5] | 0.142 ❌ | 1.000 | 0.135 | 0.853 | peggiora entrambi i lati |
| M3 astensione τ=0.5 | **0.069** ✅ | 1.000 | 0.103 | 0.837 | = M0 sul flip (nessuna astensione: \|s\| resta grande) |
| **M4 soft** | **0.071** ✅ | 1.000 | **0.099** ✅ | 0.796 ❌ | **unica** con ECE pulito e ECE_ε20 ≤ 0.10; AUC_ε20 sotto 0.85 |
| M5 combo | 0.161 ❌ | 1.000 | 0.085 | 0.854 | come M1: regolarizzazione costa il pulito |

Temperature fittate:
- M0: T_presente=0.010, T_assente=98.1
- M1 λ=0.05 (scelta sul fit per NLL_reg): T_presente=0.891, T_assente=11.7
- M2: T_presente=0.203, T_assente=4.92

## Feature-drop δ=0.20 (nasconde il match del truth)

| mappa | ECE | AUC | astensioni |
|---|---:|---:|---:|
| M0 | 0.009 | 1.000 | 0 |
| M3 | 0.096 | 1.000 | **12** |
| M4 | 0.074 | 1.000 | 0 |
| M5 | 0.187 | 1.000 | 12 |

Qui l'astensione **scatta** (12 casi): il segnale lessicale manca e M3
ricala su T_globale. Sul flip di etichetta non scatta — perché il flip
inverte un segnale ancora *forte*. Due regimi di errore diversi chiedono
due difese diverse.

## Cosa abbiamo imparato (il meglio del run)

1. **Ammorbidire T (M1/M2) migliora la coda di contaminazione e rovina il
   laboratorio.** ECE pulito 0.069 → 0.14–0.16. Non è accettabile come
   sostituto di M0: tradisce RUN5.
2. **L'astensione (M3) non aiuta il flip di etichetta** — aiuta il
   *feature-drop*. Difesa giusta per «non so se l'evidenza c'è», non per
   «ho etichettato al contrario con sicurezza».
3. **M4 (soft) è il candidato serio:** tiene il laboratorio (ECE 0.071) e
   porta ECE a ε=0.20 sotto soglia (0.099). Fallisce solo il vincolo
   AUC≥0.85 (fa 0.796). È il punto Pareto migliore rispetto a M0.
4. **Non esiste gratis:** o tieni ECE pulito da laboratorio e accetti AUC
   più bassa sotto errore, o irrigidisci la robustezza e perdi il laboratorio.

## Raccomandazione operativa (non eseguita — solo detta)

Per produzione, la mappa da portare avanti è **M4 soft** come default di
calibrazione condizionata, con **M3-astensione in cascella** quando il
soft-score è vicino a zero (feature ambigua) — cioè M4+astensione senza
regolarizzare T agli estremi. Va pre-registrata come RUN8 e misurata; non
è stata una delle mappe M0–M5 così composte.

Il miglioramento vero dei «numeri di sopravvivenza» non è un T diverso: è
**un detector che sbaglia di meno** (segnali strutturali del harness + campi
PCT). M4 compra circa 0.004 di ECE a ε=0.20 rispetto a M0 (0.103→0.099)
e ~4 punti di AUC persi: è un trade piccolo. Il salto grande resta sulla
leva 1 della sessione precedente.

*Analisi appaiata, stessi 120 logit seed 2026, zero chiamate all'engine.*
