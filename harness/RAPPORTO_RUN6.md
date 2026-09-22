# Rapporto RUN6 — quanto sopravvive fuori dal laboratorio?

Pubblicato come da regola. Metodo: `PREREGISTRAZIONE_RUN6_TWOONESYS.md`.
Sola lettura sui logit già raccolti (seed 42 fit / seed 2026 eval). Nessuna
modifica a engine, banco, o rapporti RUN2–5.

## Risposta in una riga

> **Alla sola rimozione della pulizia (1) — condizione oracolo → rilevata —
> su questo banco sopravvive il 100% della proprietà** (ECE 0.069, AUC 1.000).
> Il detector dichiarato indovina 120/120. La curva di contaminazione mostra
> però che la proprietà è **fragile rispetto all'errore di rilevazione**.

## Controllo e braccio principale

| mappa | AUC | ECE |
|---|---:|---:|
| oracolo fine (riproduce RUN5) | 1.000 | 0.069 |
| oracolo binario (presente/assente) | 1.000 | 0.069 |
| **rilevato (detector §2.2)** | **1.000** | **0.069** |
| globale T=3.947 | 0.691 | 0.182 |
| nulla T=1 | 0.663 | 0.294 |

Accuratezza detector: **120/120 (1.000)**. Affermazione RUN6: **sostenuta**.
Controllo oracolo: OK (riproduce RUN5).

## Curva di degradazione (flip ε delle etichette del detector)

| ε | AUC | ECE |
|---:|---:|---:|
| 0.05 | 0.983 | 0.030 |
| 0.10 | 0.943 | 0.013 |
| 0.20 | 0.837 | **0.103** (> 0.10) |

Lettura: con errori di rilevazione l'AUC decade in modo monotono. L'ECE non
è monotona (a ε piccoli può *scendere* per artefatto di binning su questo
insieme) — a ε=0.20 supera la soglia. **Il prezzo reale della rilevazione
imperfetta si vede sull'AUC e sul varco ECE a ε≥0.20.**

## Limite dichiarato (già in pre-registrazione §5)

Questo run ha tolto **solo** la pulizia (1): condizione data → rilevata.
Le pulizie (2) e (3) restano: su seed 2026 gli esiti sono ancora A=B=1.0,
C=0.0, e non ci sono stati ambigui. Perciò «sopravvive al 100%» significa
*sopravvive al passaggio oracolo→detector su un banco dove il detector è
perfetto per costruzione del testo*. Non significa ancora «sopravvive al
mondo reale».

Il prossimo stress (dichiarato, non eseguito): contaminare il **banco** —
esiti che si sovrappongono fra condizioni, stati con evidenza parziale —
e/o misurare su log reali coi due campi di PCT.
