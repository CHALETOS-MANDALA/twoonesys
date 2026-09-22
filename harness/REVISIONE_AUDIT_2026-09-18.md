# Revisione dell'audit `AUDIT_CASCADE_SYSTEM_ONE_2026-09-17.md`

**Metodo:** artefatti letti direttamente da `cascade/run/` sul PC. Non ho rieseguito la
suite (torch assente nel container) né le prove live KIARNEL/Ollama: quelle restano tue.

---

## 1. La tesi centrale regge

La definizione — *harness System One che governa modelli e strumenti, non un modello* — è
corretta e il codice la sostiene. Il confronto con Jev in §7 è giusto, e la frase di §10
sul **dove finisce l'errore** è la cosa migliore del documento: è un argomento tecnico
vero, non retorica.

Anche la distinzione di §8 (*"System One operativo circoscritto e verificato: sì;
production-ready generale: no"*) è la formulazione onesta.

**Una correzione che mi riguarda:** in §3.4 KIARNEL risulta collegato tramite il worker
`kiarnel.verify`. La mia affermazione precedente — *"Kiarnel è accanto, non sotto CASCADE"* —
è **superata**: `workers.py` è cresciuto da 11.752 a 14.281 byte, coerente con l'aggiunta.
Le prove live (401 / 403 `KIARNEL_PATH_DENIED` / 200) non le ho riprodotte.

---

## 2. Il punto che va corretto: §5 dice una cosa che i dati non dicono

Il documento afferma:

> CASCADE **ora registra** esplicitamente: `selection_probability`, `contract_digest`,
> `label_source`

Letti i log reali:

| log | record | `selection_probability` | `label_source` | `contract_digest` |
|---|---|---|---|---|
| `run/outcome_log.jsonl` | 40 | **0/40** | 0/40 | 0/40 |
| `run/lbp_cascade.jsonl` | 2 | **0/2** | 2/2 | 2/2 |
| `run/world_smoke.jsonl` | 4 | **0/4** | 0/4 | 0/4 |

**Zero su quarantasei.** Il campo esiste nello schema — l'ho aggiunto io — ma nessuna
decisione lo scrive. `off_policy_ready` è `False` su tutti e tre i log.

La formulazione corretta è *"CASCADE **può** registrare"*, non *"registra"*. E non è una
sfumatura: la propensione è **l'unico dato che non si recupera a posteriori**. Quelle 46
decisioni sono definitivamente inutilizzabili per una stima off-policy. Ogni run fatto da
qui in avanti senza quel campo è dato perso nello stesso modo.

I due record di `lbp_cascade.jsonl` mostrano che il workflow integrato *sa* riempire
`label_source` e `contract_digest`: manca solo il terzo, ed è quello che costa di più
ometterlo.

---

## 3. I 40 esiti sono persistenza reale, ma come dato di calibrazione valgono zero

`outcome_log.jsonl`: **40 record, `outcome = True` in 40 su 40.**

Una label costante non porta informazione: su un insieme senza varianza non si stima nessuna
curva di affidabilità, non si calcola un ECE sensato, e conformal non ha niente da separare.
La prova dimostra che **il tubo funziona** (scrittura, restart, metriche identiche) — che era
il punto di §4.3 — ma non che **la misura è cominciata**.

Il log migliore che hai è `world_smoke.jsonl`: 4 record con `True`, `False` e un `None`.
Quattro sono pochi, ma quello è l'unico che esercita davvero i tre stati del contratto,
Indeterminate compreso.

---

## 4. La prova di mutazione è sotto-dimensionata

§6 riporta **una** mutazione che fa cadere **un** test su 27, e ne conclude che la suite
«non è una collezione di test che passa per caso».

Una mutazione che uccide un test è il segnale **minimo**, non una dimostrazione. Per
confronto, sulla stessa base di codice: rimettere `float()` nel confronto delle cifre fa
cadere **12** test, togliere la propensione dal record ne fa cadere **7**. Un kill di 1/27
non distingue una suite robusta da una che copre per caso quella riga.

E c'è una ragione specifica per non poggiarsi su questo argomento **in questo progetto**: la
suite era verde anche quando il guard Z3 approvava un paziente allergico se dimenticavi un
campo, e quando la barriera respingeva metà dei claim veri. Due volte.

**Come rafforzarla, a costo quasi zero:** un insieme di mutazioni, una per proprietà critica
(binding mancante, premesse contraddittorie, `unknown` → permit, prefisso delle cifre, segno,
propensione, `solver_status` dal flag, stato fuori dall'hash), con il tasso di kill
pubblicato. Se una proprietà sopravvive alla sua mutazione, quella proprietà non è provata.

---

## 5. Tre affermazioni da etichettare meglio

**§4.2 — il fallback Ollama.** `qwen3.5:27b → HTTP 500 → deepseek-r1:7b → succeeded`
dimostra che il routing regge un guasto di infrastruttura. Non tocca il piano decisionale:
è logica di retry, non comportamento System One. Va tenuto, chiamandolo così.

**§4.7 — la catena LBP.** Un run end-to-end è una **dimostrazione**, non una misura. Il
documento è rigoroso altrove (*"deve essere misurata, non dichiarata"*) e qui scivola. Con
`n = 1` non si dice nulla su affidabilità, latenza o tasso di successo.

**§4.1 — «323 passed».** Non l'ho verificato: qui giro 259 senza torch. Non lo contesto, ma
nel documento andrebbe scritto da chi e su quale macchina.

---

## 6. L'argomento più forte che il documento non usa

§8 elenca «suite completa verde» tra le prove di maturità. È la mossa più debole del
documento, perché questo progetto ha già dimostrato due volte che un verde non prova niente.

L'argomento vero è disponibile ed è migliore:

> In due revisioni indipendenti sono stati trovati due fail-open silenziosi sotto una suite
> verde — il guard Z3 che approvava con un simbolo non legato, e la barriera che respingeva
> il 50% dei claim fedeli — entrambi chiusi con test di regressione e prova di mutazione.

Quello non dice «il codice è buono». Dice **«il processo trova i propri buchi»**, che è
l'unica cosa che un lettore esterno può davvero valutare, e che quasi nessun progetto può
mostrare.

---

## 7. Cosa cambierei, in ordine

1. **§5**: «registra» → «può registrare», con il numero reale (0/46) e la conseguenza
   dichiarata: quelle decisioni non sono recuperabili per una stima off-policy.
2. **Scrivere la propensione al momento della scelta**, ovunque si decida. È una riga, e
   ogni run senza è dato perso per sempre.
3. **§6**: insieme di mutazioni con tasso di kill, non una singola.
4. **§4.2 / §4.7**: etichettare come «prova di robustezza infrastrutturale» e
   «dimostrazione end-to-end, n=1».
5. **§8**: sostituire «suite verde» con i due fail-open trovati e chiusi.
6. **§4.3**: aggiungere che i 40 esiti hanno label costante, quindi provano la persistenza e
   non la calibrazione.

---

## 8. Il prossimo traguardo, detto in un numero

Il documento chiude su *cosa CASCADE è*. La cosa che chiuderebbe davvero la questione non è
altra prosa né un'altra integrazione: è **la prima curva di affidabilità con varianza vera**.

Oggi: 46 decisioni, una label costante su 40, propensione a zero.
Serve: **≥ 100 decisioni con esiti variati e la propensione scritta quando si decide.**

Fino a lì, ogni frase su CASCADE resta un'affermazione sull'architettura. Da lì in poi
diventa un numero — ed è l'unica cosa che né Jev né nessun altro può contestarti.
