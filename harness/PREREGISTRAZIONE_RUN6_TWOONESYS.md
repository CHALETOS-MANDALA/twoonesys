# Pre-registrazione — Run 6: quanto della proprietà sopravvive fuori dal laboratorio?

**Stato: CONGELATA dal commit che introduce questo file.**

| | |
|---|---|
| Autore | Rubinho |
| Data | 2026-09-21 |
| Proponente | 4B Q8, logit crudi + temperatura per condizione |
| Domanda | Quanto della proprietà misurata in RUN5 sopravvive quando togliamo le condizioni pulite del laboratorio? |

---

## 0. Cosa rendeva «pulito» il laboratorio di RUN5 (dichiarato)

Tre pulizie, non una:

1. **Condizione oracolo**: la fascia A/B/C era *data* dal banco, non rilevata.
2. **Separazione degli esiti**: su seed 2026, A=1.00, B=1.00, C=0.00 —
   la condizione *determinava* l'esito. L'AUC 1.0 riflette quella struttura.
3. **Condizione binaria netta**: evidenza presente (A/B) vs assente (C), senza
   stati ambigui.

RUN5 ha dimostrato: *se* la condizione è nota e netta, la calibrazione
condizionata chiude (ECE 0.069). RUN6 chiede quanto resta quando (1) e/o
(2) e/o (3) si allentano.

## 1. L'unica affermazione da misurare

> Con la temperatura fittata come in RUN5 (seed 42) e la condizione
> **rilevata** da un detector dichiarato (§2), non oracolo, sulla
> popolazione seed 2026: ECE ≤ 0.10 e AUC ≥ 0.70.

Se l'affermazione cade, si pubblica *quanto* decade rispetto all'oracolo
(controllo appaiato), non una scusa.

## 2. Disegno

### 2.1 Controllo appaiato (laboratorio, riproduzione)

Stessa popolazione seed 2026, stessa mappa T per fascia oracolo: deve
riprodurre RUN5 (ECE ≈ 0.069, AUC ≈ 1.0). Se non riproduce, STOP — bug,
non misura.

### 2.2 Braccio principale: condizione rilevata

Detector dichiarato, **pre-decisione**, senza accesso alla fascia oracolo:

```
evidenza_presente  ⇔  il testo dello stato contiene il valore-verità
                      di n (troncato a 4 dp) OPPURE contiene la frase
                      «valore confermato»
evidenza_assente   ⇔  altrimenti
```

Mappa di calibrazione collassata (coerente col reverse engineering):

- `evidenza_presente` → T = T_A = T_B del fit RUN5 (griglia estesa)
- `evidenza_assente`  → T = T_C del fit RUN5

(A e B condividevano T≈0.01; C aveva T≈100. Il detector non distingue
A da B — e non deve: la struttura misurata era binaria.)

### 2.3 Curva di degradazione (contaminazione)

Sullo stesso set, si sostituisce una frazione `ε ∈ {0.05, 0.10, 0.20}`
delle etichette del detector con il flip (seed 7). Si riporta ECE(ε) e
AUC(ε). Non decide l'affermazione: descrive quanto la proprietà dipende
dall'accuratezza del detector.

### 2.4 Invariato

Fit set seed 42, eval seed 2026, stessi logit già raccolti in
`run/run5_eval/` (argmax invariante → stessi esiti). Nessuna nuova
chiamata all'engine necessaria per il braccio principale. Baseline:
T globale 3.947, T=1.

## 3. Predizioni dichiarate in anticipo

1. Il controllo oracolo riproduce RUN5.
2. Il detector su questo banco avrà accuratezza alta (gli stati A/B
   contengono il valore; gli stati C no) — ma **non è garantito al 100%**:
   se l'accuratezza del detector è < 100%, ECE e AUC scenderanno rispetto
   all'oracolo. Quanto scendono è la misura.
3. ECE(ε) cresce con ε; la pendenza è il prezzo dell'errore di rilevazione.

## 4. Cosa falsifica

- Controllo oracolo non riproduttibile → bug, run annullato.
- Detector: ECE > 0.10 o AUC < 0.70 (o IC95 che contiene 0.5) → la
  proprietà **non** sopravvive al passaggio oracolo→rilevazione su questo
  banco, alle soglie dichiarate.
- **Il rapporto si pubblica in tutti i casi.**

## 5. Limite dichiarato (parte del risultato)

Questo run toglie la pulizia (1). Le pulizie (2) e (3) restano in parte:
il banco seed 2026 ha ancora esiti nettamente separati, e non introduce
stati ambigui. Un RUN successivo dovrà contaminare *il banco* (esiti che
si sovrappongono fra condizioni; stati con evidenza parziale). Dichiarato
qui perché non si confonda «sopravvivenza alla rilevazione» con
«sopravvivenza al mondo reale».

## 6. Firma

```
data: 2026-09-21
commit: (il commit che introduce questo file congela il metodo)
```
