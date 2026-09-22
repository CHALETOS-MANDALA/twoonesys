# Pre-registrazione — Run 8: detector strutturale vs M4-soft testuale

**Stato: CONGELATA dal commit che introduce questo file.**
Nessuna riga si tocca dopo il congelamento. Emendamenti solo in documenti
datati successivi. **§6 tolleranze:** chiuse da
`EMENDAMENTO_RUN8_TOLLERANZE_2026-09-21.md` (solo numeri da §6.1 / RUN5–7).
OOD eseguibile solo dopo quel emendamento (già presente).

| | |
|---|---|
| Autore | Rubinho |
| Data | 2026-09-21 |
| Pipeline sotto misura | `input → detector → P(evidenza) → M4 soft → confidence calibrata → policy` |
| Variabile unica | il **detector** (testuale vs strutturale). Tutto il resto è identico e appaiato. |

---

## 1. Ipotesi congelate

**H0:** il detector strutturale **non** migliora M4-soft fuori distribuzione
(OOD appaiato).

**H1:** il detector strutturale mantiene sostanzialmente il comportamento
in-distribution di M4-soft, ma **degrada meno** sotto perturbazioni che
rompono le scorciatoie testuali.

Il match testuale attuale **non si elimina**: resta la baseline M4
(preziosa proprio perché fa 120/120 sul banco e sfrutta una rappresentazione
fragile). Il detector strutturale è un braccio nuovo, non un sostituto
silenzioso.

---

## 2. Contratto del detector

### 2.1 Baseline — detector testuale (M4-soft attuale)

Determina `s` / `P(evidenza presente)` dalle **parole** nello stato
(soft-score RUN7 §2.1: presenza di `truth_4dp`, «valore confermato»,
«non disponibile» / «ancora in corso», altri zeri nel testo).

### 2.2 Braccio nuovo — detector strutturale

Determina `P(evidenza presente)` **solo** da fatti osservabili prodotti
dal sistema, non dal lessico del prompt. Fonti ammesse (dichiarate):

| Fonte | Segnale ammissibile |
|---|---|
| Kernel / claim barrier | evidenza `zeron` calcolata; `verdict.ok` / codice verdetto |
| PRISM | score di pertinenza documenti recuperati (se presenti) |
| Engine | `status` tipizzato (`ok` / `insufficient_evidence` / …), non il testo della domanda |
| Provenance | digest/contratto, `label_source`, presenza di receipt di verifica |
| Verifica | esito di `run_verified` già avvenuto sul caso (se nel record) |

**Vietato** al detector strutturale: leggere il campo `rapporto` / prompt per
decidere presenza di evidenza; usare la fascia oracolo del banco; usare
l’esito `outcome` (sarebbe circolare).

Output di entrambi i detector: uno score `s ∈ ℝ` (o probabilità in [0,1])
che entra nello **stesso** M4 soft (stesse T_presente / T_absent di RUN7 M0,
stessa formula soft). Poi stessa confidence, stessa policy, stesso scoring.

### 2.3 Confronto appaiato (invariante)

```
stesso caso C
    ├─ detector_testuale(C)  → s_t → M4 → conf_t → policy → metriche
    └─ detector_strutturale(C) → s_s → M4 → conf_s → policy → metriche
```

Una sola variabile cambia. Qualunque differenza downstream è attribuibile
al detector.

---

## 3. Due popolazioni, dichiate ora

### 3.1 In-distribution (laboratorio)

La popolazione seed 2026 già usata in RUN5–7 (120 casi, logit già raccolti).
Qui il testuale è forte per costruzione. Serve a verificare che lo
strutturale **non rovini** il laboratorio (preservazione).

### 3.2 OOD — testo e struttura deliberatamente divergono

Non basta parafrasare le frasi (sarebbe un altro test linguistico). Ogni
caso OOD dichiara una **divergenza** fra ciò che dice il testo e ciò che
dice lo stato strutturale. Tipi congelati (almeno uno slot per tipo nel
banco OOD; numerosità totale fissata in §6 prima del run):

| id | Divergenza |
|---|---|
| D1 | testo dice che l'evidenza **esiste**; struttura dice **assenza** |
| D2 | testo dice che **manca**; struttura contiene evidenza **verificata** |
| D3 | evidenza presente ma **incompleta** |
| D4 | evidenza presente ma **stale** (fuori finestra di validità dichiarata) |
| D5 | fonte presente ma **verifica fallita** |
| D6 | **più fonti in conflitto** |
| D7 | status **ambiguo / unknown** |
| D8 | componente strutturale **mancante o irraggiungibile** |

Questi casi distinguono «legge lo stato del mondo del sistema» da
«ha trovato un’altra scorciatoia».

---

## 4. Metriche congelate (tre livelli)

La accuracy del detector è **intermedia**. La domanda di TWOONESYS è
downstream.

### 4.1 Detector (intermedie)

- AUROC / AUPRC rispetto all’etichetta strutturale di ground truth del caso
  (dichiarata nella costruzione OOD; in-distribution: presente ⇔ fascia A∪B)
- Brier / NLL dello score del detector
- Confusion matrix (soglia operativa dichiarata in §6, derivata dal protocollo)

### 4.2 TWOONESYS (primarie di calibrazione)

- ECE (10 bin, come RUN2–7)
- Brier della confidence calibrata vs outcome
- NLL della confidence calibrata vs outcome

### 4.3 Decisione (primarie di policy)

- Error rate complessivo
- False authorization (approved∧¬outcome) e false rejection (¬approved∧outcome)
  dove applicabile al contratto del caso
- Coverage se c’è astensione del detector (frazione di casi su cui si emette
  una decisione calibrata invece di escalare / T_globale)

---

## 5. Criterio di successo (forma congelata; numeri in §6)

Il detector strutturale **vince** su H1 (e H0 è rifiutata) se e solo se
**tutte** le condizioni seguenti valgono:

1. **Preservazione laboratorio:** sulle metriche TWOONESYS in-distribution,
   lo strutturale resta entro le tolleranze di §6 (derivate dal protocollo
   già pubblicato), rispetto a M4-testuale appaiato.
2. **Miglioramento OOD:** sulle metriche TWOONESYS (e/o decisione) nei casi
   OOD appaiati, lo strutturale produce un miglioramento
   **statisticamente verificabile** rispetto a M4-testuale, secondo il test
   dichiato in §6.
3. **Nessun peggioramento critico:** nessuna metrica critica di §6 peggiora
   oltre la soglia preregistrata lì.

Se (1)∨(2)∨(3) fallisce → H0 non rifiutata; si pubblica il confronto
appaiato comunque.

---

## 6. Tolleranze numeriche — SOLO da protocollo già pubblicato

**Regola:** nessun numero nuovo inventato in questa sezione. Solo valori
già scritti in `PREREGISTRAZIONE_RUN2`, rapporti RUN5–7, o formule su di essi.
Questa sezione va **completata e re-committata** prima del primo run OOD.
Fino ad allora RUN8 è congelato nel metodo ma **non eseguibile**.

### 6.1 Ancoraggi già pubblicati (non negoziabili)

| Ancoraggio | Valore | Fonte |
|---|---|---|
| Soglia ECE primaria del protocollo | ≤ 0.10 | RUN2 §1 / RUN5 §1 |
| Soglia AUC primaria del protocollo | ≥ 0.70 | RUN2 §1 / RUN5 §1 |
| ECE M4-soft in-lab (seed 2026) | 0.0713 | RUN7 |
| ECE M0/M4-dura in-lab | 0.0691 | RUN5 / RUN6 / RUN7 |
| ECE M4 a ε=0.20 (flip etichetta) | 0.0988 | RUN7 |
| ECE M0 a ε=0.20 | 0.1029 | RUN6 / RUN7 |
| Margine lab M4 sotto soglia | 0.10 − 0.0713 = **0.0287** | derivato |

### 6.2 Tolleranze — CHIUSE

Vedi `EMENDAMENTO_RUN8_TOLLERANZE_2026-09-21.md`. Riepilogo operativo:

- Lab: ECE ≤ 0.10, AUC ≥ 0.70, ΔECE vs M4-testuale ≤ 0.0287
- OOD primaria: ECE; miglioramento = IC95 bootstrap B=2000 seed=8 di
  (ECE_testuale − ECE_strutturale) esclude 0
- n OOD = 96 (12 × D1..D8)
- Detector: AUROC/AUPRC primarie; confusion a soglia s=0 (come RUN6/7)
- Critica: non peggiorare ECE (né false-authorization dove definita) vs testuale

Fino a questo emendamento RUN8 non era eseguibile; ora il metodo è completo.

---

## 7. Cosa si può fare dopo questo congelamento

1. Interfaccia del detector strutturale (fatti tipizzati → score).
2. Generatori casi D1–D8 (validazione meccanica della divergenza dichiarata,
   senza tuning sui detector).
3. Eval appaiato in-distribution (seed 2026) poi OOD n=96.

**Vietato:** eliminare la baseline testuale; scegliere iperparametri del
detector guardando metriche OOD prima del rapporto.

---

## 8. Relazione con RUN precedenti (invariata)

- RUN5: calibrazione condizionata chiude se la condizione è nota.
- RUN6: sopravvive al passaggio oracolo→rilevazione se il detector è perfetto.
- RUN7: M4 soft è il miglior trade lab/robustezza fra mappe T; il salto
  grande è il detector.
- **RUN8:** misura se uno strutturale batte il testuale dove le scorciatoie
  lessicali sono costruite per mentire.

---

## 9. Firma

```
data: 2026-09-21
commit: (il commit che introduce questo file congela metodo, H0/H1,
         OOD types, metriche, forma del successo; §6 checklist aperta)
```
