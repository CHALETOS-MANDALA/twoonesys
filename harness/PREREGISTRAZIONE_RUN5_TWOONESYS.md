# Pre-registrazione — Run 5: la calibrazione è componibile? (verdetto fuori campione)

**Stato: CONGELATA dal commit che introduce questo file.**

| | |
|---|---|
| Autore | Rubinho (metodo ereditato: RUN1 → RUN4) |
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine 4B Q8, logit crudi + **temperatura per condizione** applicata dal harness |
| Base esplorativa | `reverse_calibration.py` sul fit set seed 42 (in-sample, dichiarato) |

---

## 1. L'unica affermazione da misurare

> Con la temperatura **condizionata** fittata come in §2, la confidenza
> sull'insieme di valutazione è calibrata con **ECE ≤ 0.10** su 10 bin e
> discrimina con **AUC ≥ 0.70** — fuori campione.

## 2. Disegno dichiarato

- **Condizione**: la fascia del banco (A/B/C), nota **pre-decisione** per
  costruzione. Dichiarato: in produzione la condizione «evidenza presente /
  assente» va *rilevata* (è il territorio del detector di PCT); qui la
  condizione è data, e ciò che si misura è se la calibrazione condizionata
  chiude l'errore che la globale non chiude.
- **Fit**: temperature per condizione sulle 120 righe `LabeledLogits` seed 42
  (le stesse di RUN4), griglia estesa T ∈ [0.01, 100] (RUN4 ha mostrato i fit
  ai bordi della griglia vecchia: conta la direzione, ma il valore va cercato
  dove vive).
- **Valutazione**: la popolazione seed 2026 — **la stessa di RUN4**. I logit
  crudi si ri-raccolgono (l'engine è deterministico; `option_logits` nella
  risposta sono pre-temperatura). L'argmax è invariante sotto temperatura →
  gli esiti sono identici per costruzione: cambia solo la confidenza. Il
  confronto RUN4 (globale) vs RUN5 (condizionata) è quindi **appaiato**:
  stessi casi, stessi esiti, diversa mappa di calibrazione.
- **Applicazione harness-side**: l'engine resta grezzo; la temperatura per
  condizione è applicata dal banco ai logit. Coerente con l'architettura:
  la calibrazione è del harness, non del modello.

## 3. Predizioni dichiarate in anticipo

1. **ECE scende sotto 0.10** (in-sample la composta vale 0.080 vs 0.167 della
   globale; fuori campione ci si aspetta peggio — quanto peggio è la misura).
2. **AUC migliora** rispetto a RUN4 (0.691): schiacciare la confidenza della
   fascia C (dove vivono i fallimenti) e alzare quella di A/B migliora
   l'ordinamento globale. Non è un'invarianza: è una predizione.
3. Se entrambe reggono, la calibrazione del cancello è **componibile**:
   componenti per condizione, non uno scalare globale.

## 4. Cosa falsifica l'affermazione

- ECE > 0.10 fuori campione → la componibilità non generalizza (almeno non
  con 40 esempi per condizione).
- AUC < 0.70 o IC95 che contiene 0.5 → la confidenza condizionata non
  discrimina.
- **Il rapporto si pubblica in tutti i casi.**

## 5. Invariato

Oracolo, fasce, baseline B0/B1/B2, esclusioni, propensione 1.0 dichiarata,
pubblicazione garantita. La regola di arresto qui non si applica come negli
altri run: la valutazione è una ri-scansione deterministica della popolazione
seed 2026 già misurata (120/40), dichiarato in §2.

## 6. Firma

```
data: 2026-09-21
commit: (il commit che introduce questo file congela il metodo)
```
