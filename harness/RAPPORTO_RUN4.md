# Rapporto RUN4 — la calibrazione chiude la catena? No. E il perché è il risultato.

Pubblicato come da §8: **qualunque sia l'esito**. Metodo:
`PREREGISTRAZIONE_RUN4_TWOONESYS.md` (congelata prima del fit). Fit: 120 righe
`LabeledLogits` da casi seed 42 sull'engine non calibrato → temperatura
`numeric` **T = 3.947** (NLL 2.157 → 1.206 sul fit). Valutazione: seed 2026,
casi mai visti dal fit. Dati: `run/run4/run4.jsonl` (120 valide, 40
fallimenti, 0 nulli), analisi in `run4.analysis.json`.

| | |
|---|---|
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine 4B Q8 + temperatura T=3.947 (fingerprint-vincolata) |

## Esito: NON sostenuta — ma la metà che migliora e la metà che resiste dicono cose diverse

| Metà | Risultato | Verdetto |
|---|---|---|
| **Discriminazione** | AUC = **0.691**, IC95 [0.596, 0.787] | regge debolmente: esclude 0.5, sotto la soglia-punto 0.70 |
| **Calibrazione** | ECE = **0.182** | **cade**, ma: era 0.282 |

## I tre numeri che raccontano la storia

| | RUN3 (grezza) | RUN4 (T=3.947) | Lettura |
|---|---:|---:|---|
| ECE fuori campione | 0.282 | **0.182** | la temperatura generalizza: −36% di errore di calibrazione su casi mai visti |
| AUC | 0.775 | 0.691 | la temperatura è monotona: il calo è variazione di campione (seed diverso → istanze diverse; B: 0.78→1.00), non segnale rotto |
| Fascia C | 0/40 | 0/40 | **immutata**: dove manca l'evidenza, il 4B sbaglia sempre |

## La scoperta strutturale (il vero risultato di RUN4)

Una temperatura è **un aggregato**: un solo scalare per tutte le decisioni.
RUN4 dimostra su dati reali la tesi di PCT: l'aggregato ammorbidisce
l'errore medio ma è **strutturalmente cieco** al fallimento concentrato in una
condizione. La fascia C (evidenza mancante) resta a zero successi con
confidenza ancora alta: nessun T globale può sgonfiare la confidenza
*specificamente* quando l'evidenza manca, perché T non vede la condizione.

La catena «segnale → misura → calibrazione → confidenza onesta» si è chiusa
a metà: la calibrazione aggregata funziona (ECE −36% fuori campione) e **non
basta**. Il passo successivo non è una temperatura migliore: è una
calibrazione **condizionata** (per disponibilità di evidenza) o l'astensione
(`allow_abstain=true`) che escala al System 2 invece di indovinare — cioè
esattamente la memoria episodica/condizionale di cui PCT misura il
valore.

## Baseline (dichiarate prima)

- **B0**: ECE 0.000, AUC 0.5 — calibrata e inutile, la trappola sempre in agguato.
- **B1** (soglia 0.9): accuratezza 0.333 — con la confidenza ricalibrata la
  soglia fissa collassa: altro segno che la grezza non era una probabilità.
- **B2** (casuale): AUC 0.464.

## Stato della catena dopo RUN4

1. Il segnale c'è (AUC > 0.5 con IC che lo esclude, in tre run su tre). ✅
2. La misura è onesta (metodo congelato, esiti pubblicati anche perdenti). ✅
3. La calibrazione aggregata aiuta ma non basta (ECE 0.182 > 0.10). ⚠️
4. Serve la componente condizionale/episodica — la domanda di PCT,
   ora con evidenza reale nel nostro dominio. ⬅️ **qui si va**

*Analisi eseguita solo dopo la soglia (120/40), come da regola di arresto.*
