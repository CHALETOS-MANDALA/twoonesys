# Pre-registrazione — Run 1 di calibrazione CASCADE

**Stato: BOZZA.** Va congelata (commit + digest) **prima** di lanciare qualunque run.
Da quel momento nessuna riga si tocca: le modifiche vanno in un documento successivo, datato,
che dichiara cosa è cambiato e perché.

| | |
|---|---|
| Autore | Rubinho |
| Data di congelamento | 2026-09-20 |
| Commit che la congela | *(hash del primo commit git di cascade/)* |
| Digest del contratto misurato | `integrated-workflow-v1` |

---

## 1. L'unica affermazione da misurare

> Sullo schema decisionale dichiarato in §2, la confidenza emessa dal sistema **predice**
> il successo dell'esito con AUC ≥ 0.70, **ed è calibrata** con ECE ≤ 0.10 su 10 bin.

Una sola frase. Tutto ciò che non serve a sostenerla o a falsificarla è fuori da questo run.

Le due metà non sono intercambiabili e vanno pubblicate insieme: un predittore costante al
tasso base è **perfettamente calibrato e inutile**; un predittore che discrimina bene può essere
sistematicamente sovra-confidente. Nessuna delle due da sola sostiene l'affermazione.

---

## 2. Definizione operativa dell'esito (l'oracolo)

### 2.1 Come nasce il claim

```
compito con risposta verificabile per cifre
        ↓
il MODELLO produce la risposta            ← il claim nasce qui, e solo qui
        ↓
il claim entra nella barriera
        ↓
CalcKernel produce l'evidenza indipendente ← l'oracolo giudica, non suggerisce
        ↓
outcome = le cifre del claim combaciano con l'evidenza alla precisione dichiarata
```

**Vincolo non negoziabile:** il valore del claim deve provenire dalla risposta del modello.
Se proviene dall'evidenza, l'esito non misura il modello.

### 2.2 Il difetto attuale che questo vincolo chiude

`workers.py:359-366` costruisce il claim dalle cifre del kernel stesso:

```python
first = expected_list[0]                      # evidence["fact"]["expected"][0]
claim = NumericClaim(..., value=float(first["value"]), ...)
verdict = check_numeric_claim(claim, evidence) # confronta l'evidenza con se stessa
```

`run_verified()` **non ha alcun parametro** attraverso cui una risposta del modello possa
entrare. Eseguito con backend iniettati ed evidenza a 37 decimali
(`14.1347251417346937904572519835624702707`):

```
precision=10  ok=True    claim.value=14.134725141734695
precision=15  ok=False   claim.value=14.134725141734695
precision=17  ok=False   claim.value=14.134725141734695
precision=20  ok=False   claim.value=14.134725141734695
precision=37  ok=False   claim.value=14.134725141734695
```

Due regimi, entrambi **costanti e indipendenti da qualunque modello**: sotto la soglia di
float64 passa sempre, sopra fallisce sempre — e il fallimento è un artefatto della conversione
`float()`, non una risposta sbagliata. L'esito è funzione del parametro `precision`, nient'altro.

**Conseguenza per il run:** il banco non può partire finché il claim non nasce dal modello e il
valore non viaggia in forma decimale esatta (`str`/`Decimal`, mai `float`).

### 2.3 Etichettatura

- `label_source = "mechanical"` — l'esito è letto da un confronto di cifre, non da un giudizio.
- L'esito è **osservato dopo** la decisione, mai derivato da `approved`.
- Test di validità dell'oracolo, prima del run: su un campione di controllo deve esistere almeno
  una coppia `approved = True ∧ outcome = False`. Se in 30 record di rodaggio non compare mai,
  l'esito è sospetto di circolarità e il run **non parte**.

---

## 3. Popolazione e stratificazione

Tre fasce di difficoltà dichiarate ora, campionate in proporzione fissa:

| Fascia | Definizione | Quota | Tasso di fallimento atteso |
|---|---|---|---|
| A — facile | precisione bassa, `n` piccolo | 1/3 | ~5% |
| B — media | precisione media | 1/3 | ~25% |
| C — difficile | precisione alta, `n` grande | 1/3 | ~50% |

Tasso di fallimento complessivo atteso: **~27%**.

Senza varianza di difficoltà non c'è niente da discriminare: la stratificazione non è un
dettaglio statistico, è la condizione perché la domanda abbia senso.

**Verifica preliminare obbligatoria:** il tasso di successo deve **differire** fra le fasce,
misurato sul rodaggio. Se le tre fasce hanno lo stesso tasso, la stratificazione non ha
funzionato e i parametri vanno ritarati **prima** del run vero (e la ritaratura va annotata qui
sotto, datata).

---

## 4. Metriche

**Primarie** (decidono l'esito dell'affermazione):

- **AUC** con IC95 (Hanley-McNeil), confidenza → esito.
- **ECE** su 10 bin di uguale ampiezza, con curva di affidabilità pubblicata.

**Secondarie** (descrivono, non decidono):

- tasso di astensione e copertura conformal empirica vs nominale (1−α);
- percentili di latenza p50 / p95 / p99, scomposti (embed / infer / verify);
- tasso di `Indeterminate` e di `INVALID_CONTEXT`.

---

## 5. Baseline, dichiarate prima

| | Descrizione | A cosa risponde |
|---|---|---|
| **B0** | predittore costante al tasso base | «la calibrazione da sola non basta» |
| **B1** | euristica attuale (soglia fissa sulla confidenza grezza) | «il calibratore aggiunge qualcosa?» |
| **B2** | confidenza casuale, stesso marginale | «il segnale non è rumore» |

L'affermazione è sostenuta solo se il sistema **batte B0 e B2 sulla discriminazione** e non
peggiora B1 sulla calibrazione.

---

## 6. Dimensione campionaria — fissata ora, non decisa guardando i dati

Hanley-McNeil, con tasso di fallimento ~25% (successi = 3 × fallimenti):

| fallimenti | totale | IC95 se AUC vera = 0.70 | se 0.80 | se 0.85 |
|---:|---:|---|---|---|
| 5 | 20 | 0.412–0.988 (±0.288) | 0.546–1.000 | 0.622–1.000 |
| 10 | 40 | 0.499–0.901 (±0.201) | 0.622–0.978 | 0.691–1.000 |
| 20 | 80 | 0.559–0.841 (±0.141) | 0.675–0.925 | 0.738–0.962 |
| **30** | **120** | **0.585–0.815 (±0.115)** | **0.698–0.902** | **0.759–0.941** |
| 50 | 200 | 0.611–0.789 (±0.089) | 0.721–0.879 | 0.780–0.920 |

**Decisione: n = 120 decisioni valide, con ≥ 30 della classe minoritaria.** Al tasso atteso
del 27% servono ~110-130 decisioni; si continua finché **entrambe** le condizioni sono
soddisfatte.

### 6.1 La regola che protegge dal racconto

Con AUC vera 0.80 l'IC95 esclude 0.5 già con **4 fallimenti**. Cioè: guardando i dati mentre
arrivano, prima o poi si vede un intervallo che «esclude il caso» — e ci si ferma lì.
È esattamente quello che è successo in questa sessione: **0.852 con 4 fallimenti, poi 0.702 con
5**, intervallo che inghiotte lo 0.5.

Quindi:

- **La regola di arresto è su `n`, mai sul risultato.** Non si guarda l'AUC prima di aver
  raggiunto 120 decisioni valide e 30 fallimenti.
- Ciò che si può guardare durante il run, senza contaminare: integrità dei record, `model_id`
  stabile, VRAM sopra il floor, buchi di cadenza, tasso di fallimento per fascia.
- Qualunque analisi fatta prima della soglia è **esplorativa** e va etichettata come tale nel
  rapporto finale, per sempre.

---

## 7. Regole di esclusione, decise ora

Un record è **nullo** (escluso dal denominatore, conservato nel log con la ragione) se e solo se:

1. il processo esecutore ha sollevato un'eccezione — registrata per intero, non solo
   `outcome=False`;
2. la VRAM libera è scesa sotto il floor dichiarato (2 GiB) durante la decisione;
3. il timeout del solver è scattato (`Indeterminate` per timeout, non per contenuto);
4. `contract_digest` differisce da quello congelato in testa a questo documento.

Un cambio di `model_id` **non** è un'esclusione: **segmenta il run in due dataset** e va
riportato come tale. Nessun'altra ragione di esclusione è ammessa dopo il congelamento.

---

## 8. Cosa falsifica l'affermazione

Dichiarato prima, così il risultato negativo non è rinegoziabile:

- **IC95 dell'AUC che contiene 0.5** a n=120 → *la confidenza non discrimina su questo schema*.
- **AUC ≥ 0.70 ma ECE > 0.10** → *discrimina ma non è calibrata*: si pubblica la distinzione,
  non si sceglie la metà che conviene.
- **Nessuna differenza fra le tre fasce** → il banco non produce varianza informativa: il
  risultato, qualunque sia, non riguarda il sistema ma il banco.

**Il rapporto si pubblica in tutti e tre i casi.**

---

## 9. Il pilota da 20 — cosa può e cosa non può dire

Il pilota serve a **tre controlli meccanici**, non a una misura:

1. la coppia `approved = True ∧ outcome = False` esiste (§2.3);
2. il tasso di fallimento differisce fra le fasce (§3);
3. telemetria completa in ogni record: `model_id`, `vram_free_mib`, latenze scomposte,
   `selection_probability`, `contract_digest`, `label_source`.

**Dal pilota non si legge alcun AUC, alcun ECE, alcuna curva.** Con ~5 fallimenti l'intervallo
è ±0.29: qualunque numero esca è compatibile sia con 0.5 sia con 0.95.

---

## 10. Propensione

Va registrata **la probabilità reale con cui il braccio è stato scelto**, al momento della
scelta, dalla politica che l'ha scelto. Non ricostruita dopo, non derivata dall'indice del
record, non assegnata per coerenza.

Se in questo run esiste una sola azione possibile, si scrive `selection_probability = 1.0` e si
dichiara qui che **nessuna stima off-policy è possibile su questi dati**. È una risposta onesta;
un numero inventato non lo è.

---

## 11. Firma

Congelando questo documento dichiaro che i criteri sopra sono stati scritti **prima** di
osservare i dati del run, e che il rapporto finale riporterà il risultato ottenuto secondo
questi criteri, qualunque esso sia.

```
data: ____________________
commit: __________________
```
