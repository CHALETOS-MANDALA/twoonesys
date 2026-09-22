# CASCADE — il piano che applicherei se fosse un progetto di laboratorio

**Data:** 2026-09-18 · **rev. 2**
**Prospettiva:** architetto backend / senior dev, con i vincoli che un'organizzazione seria
imporrebbe prima di lasciar uscire un numero.
**Base:** difetti trovati eseguendo il codice in questa sessione, non ipotesi.

### Cosa è cambiato nella rev. 2, e perché

Quattro correzioni, tre sollevate da Rubinho sulla rev. 1 e una sua scoperta nel codice:

| | rev. 1 | rev. 2 |
|---|---|---|
| §1.2 | «sostituire l'oracolo con CalcKernel + barriera» | **il pezzo mancante**: il claim deve nascere dal modello, il kernel giudica soltanto. Oggi il claim nasce dal kernel stesso (`workers.py:359-366`) — verificato eseguendo |
| §2.2 | bracci `recall.escalation` DIRECT/EPISODIC/… | **inventati**: esistono solo nei miei fixture di test. Ritirati |
| §5 | «la strategia di test ha già fallito due volte» | la **suite** era verde col bug dentro; il **metodo** è ciò che li ha trovati |
| §8 | «taglierei L2, L3, marketplace» | non è una decisione da revisore: riformulato come portata del claim |

---

## 0. La cosa che direi per prima, in riunione

> **Oggi il progetto non ha una sola affermazione misurata.**

Ha un'architettura corretta, contratti seri, due fail-open trovati e chiusi, una suite verde e
un apparato che sopravvive. Tutto vero, tutto verificato. Ma la frase che vende — *«la
confidenza è calibrata»* — non è ancora sostenuta da niente, e il banco attuale **non può**
sostenerla (§1).

Tutto il resto del piano serve a produrre quella frase, o a proteggerla.

---

## 1. Il banco di prova — la correzione che vale più di tutte le altre

### 1.1 Il difetto

```python
roll = rng.random()
hard_fail   = roll < args.fail_rate
silent_drop = (not hard_fail) and (roll < fail_rate + drop_rate)
```

Il fallimento è estratto da un RNG indipendente dalla confidenza. **L'AUC atteso è 0.5 per
costruzione**, e i dati lo mostrano già: confidenza media dei successi 0.907, dei fallimenti
0.901. Il banco misura `1 − (fail_rate + drop_rate)`, cioè un parametro scelto a riga di
comando.

### 1.2 La sostituzione

L'oracolo giusto è già in casa: **CalcKernel + claim barrier**.

```
compito con risposta verificabile per cifre
        ↓
il modello produce un claim
        ↓
outcome = "le cifre del claim combaciano con l'evidenza del kernel"
```

Questa è un'etichetta che **dipende da quanto bene il modello ha lavorato**. La confidenza ha
finalmente qualcosa da inseguire, e l'AUC può uscire 0.85 o 0.50 — in entrambi i casi hai
imparato qualcosa.

### 1.2.1 Il pezzo che rende la sostituzione non banale

Dire «CalcKernel + barriera» non basta, perché il banco **già** usa CalcKernel e la barriera, e
non misura niente lo stesso. `workers.py:359-366`:

```python
first = expected_list[0]                       # evidence["fact"]["expected"][0]
claim = NumericClaim(..., value=float(first["value"]), ...)
verdict = check_numeric_claim(claim, evidence)  # confronta l'evidenza con se stessa
```

Il claim è costruito **dalle cifre del kernel**, e `run_verified()` non espone alcun parametro
da cui una risposta del modello possa entrare. Eseguito con backend iniettati, evidenza a 37
decimali:

```
precision=10  ok=True     precision=17  ok=False
precision=15  ok=False    precision=37  ok=False    claim.value = 14.134725141734695
```

Due regimi costanti, **entrambi indipendenti da qualunque modello**: sotto la soglia di float64
passa sempre; sopra fallisce sempre, e per un artefatto di `float()`, non per una risposta
sbagliata. L'esito è funzione del parametro `precision`.

**Quindi la correzione vera è di flusso, non di componente:** il claim nasce dalla risposta del
modello, il kernel è solo l'oracolo che giudica, e il valore viaggia in forma decimale esatta
(`str`/`Decimal`) fino alla barriera — mai come `float`.

### 1.3 Stratificazione della difficoltà

Tre fasce dichiarate prima del run (es. zeri di zeta con `n` piccolo / medio / grande, o
precisione richiesta crescente), con il tasso di successo atteso diverso per fascia. Senza
varianza di difficoltà non c'è niente da discriminare, e la classe rara resta vuota.

### 1.4 Analisi di potenza, prima di lanciare

Non «facciamone 250 e vediamo». Si decide prima:

```
larghezza dell'IC accettabile per l'AUC  →  numero di esempi della classe minoritaria
                                         →  numero totale al tasso di fallimento atteso
```

Regola d'ordine: **25-30 nella classe rara** per un intervallo utile. Sotto, non si pubblica.

### 1.5 Pre-registrazione

Prima del run, in un file committato: ipotesi, metriche, baseline (B0 ramo costante, B1
euristica attuale, B2 casuale), criterio di arresto, regole di esclusione.

**Perché è la regola più importante:** in questa sessione l'AUC è passato da 0.852 a 0.702
appena è arrivato un campione in più, e l'intervallo ha inghiottito lo 0.5. Con la
pre-registrazione quel racconto non è possibile: il criterio era già scritto.

---

## 2. Decisione vera, propensione vera

### 2.1 Il difetto

```python
selection_probability = 0.25 if index % 4 == 0 else 0.75
```

La propensione è assegnata dalla parità dell'indice. **Non c'è nessuna scelta fra bracci**:
`action` è `verified_model_action` in 46 record su 46. Qualunque IPS su questi dati è
aritmetica su un'etichetta inventata.

### 2.2 La correzione

**Ritirato dalla rev. 1:** avevo proposto bracci `recall.escalation` (DIRECT / EPISODIC /
CONVERGENCE / DEEP / ABSTAIN). Quei nomi non esistono nel codice: compaiono **solo** nei fixture
che ho scritto io in `tests/test_regressioni_2026_09_18.py:142-234`. Avevo inventato un
vocabolario in un test e poi l'avevo citato come se fosse il dominio. È una feature nuova
travestita da correzione — esattamente il modo in cui un progetto si allarga invece di misurarsi.

La sostanza resta, e non richiede nessun motore nuovo:

```
chosen_arm · selection_probability · policy_version
```

La propensione dev'essere **la probabilità reale con cui il braccio è stato effettivamente
scelto**, dalla politica che l'ha scelto, al momento della scelta. Con ε-greedy su azioni che
esistono già la conosci esattamente; qualunque altra politica deve esporla.

E se in un run esiste **una sola** azione possibile, la risposta onesta è scrivere `1.0` e
dichiarare che su quei dati nessuna stima off-policy è possibile. B3 si chiude registrando la
scelta vera — non aggiungendo bracci perché il campo sia interessante.

---

## 3. L'ambiente è una covariata, non una nota a piè di pagina

### 3.1 Il difetto

6847/8151 MiB di VRAM, due processi Ollama, cadenza che oscilla **13,5-62,2 s** (fattore 4,6).
Quella dispersione è la firma di scarico/ricarica del modello sotto pressione.

Se a metà run un modello viene evitto, ricaricato, o una richiesta finisce su un fallback, **la
distribuzione della confidenza cambia** e il set di calibrazione diventa due popolazioni
diverse mescolate. È lo stesso meccanismo del cambio di regime al record 60 del run precedente:
invisibile, perché non registrato.

### 3.2 La correzione

Per **ogni** record:

```
model_id · quantization · vram_free_mib · queue_depth
latency_total_ms · latency_embed_ms · latency_infer_ms · latency_verify_ms
```

E una regola di validità: **se `model_id` cambia durante un run, il run è due dataset.** Va
segmentato, non mediato.

### 3.3 Il budget di memoria, dichiarato

Un run di misura gira con VRAM **riservata**, non condivisa. Se il bench e LATENT_BRAIN_MEMORY
si contendono la scheda, la latenza semantica che misuri è quella della contesa, non quella del
sistema. Fissa un floor (es. 2 GiB liberi) e **rifiuta di partire** sotto quella soglia, invece
di degradare in silenzio.

---

## 4. Riproducibilità: un run deve poter essere rifatto identico

- **Seed unico** per tutto (RNG, ordinamenti, campionamenti) e registrato nel manifesto del run.
- **`contract_digest`** che copre schema, scorer, feature, protocollo di etichettatura, indice,
  versioni delle librerie. Cambia qualcosa → digest diverso → il calibratore non è applicabile
  (già previsto, va popolato davvero).
- **Manifesto del run** committato accanto ai dati: comando esatto, versioni, hardware, ora.
- **Replay bit-esatto** della fase di riduzione: è pura per contratto, quindi deve esserlo per
  test. Un test di permutazione (mescola l'ordine di arrivo → stessa uscita) lo blinda.

---

## 5. Strategia di test — quello che la suite non ha visto, e chi l'ha visto

Detto preciso, perché la formulazione della rev. 1 («ha già fallito due volte») era sbagliata e
si prestava a una conclusione falsa.

**La suite è stata verde con il bug dentro, due volte:** quando il guard Z3 approvava un paziente
allergico per un simbolo non legato, e quando la barriera respingeva metà dei claim fedeli.
Questo è vero, ed è l'argomento più forte per il cancello di mutazione qui sotto.

**Il metodo non ha fallito: è ciò che li ha trovati.** Entrambi sono usciti da verifiche
indipendenti che *eseguivano* il codice invece di leggerlo. La conclusione da trarre non è «i
test non servono», è: *un verde è una condizione necessaria e non è una prova; la prova è una
mutazione che muore*.

### 5.1 La mutazione diventa un cancello di CI, non un aneddoto

Un **insieme** di mutazioni, una per proprietà critica, con tasso di uccisione pubblicato:

```
binding mancante → permit          premesse contraddittorie → permit
unknown/timeout → permit           prefisso delle cifre
segno del numero                   propensione assente
solver_status dal flag             stato fuori dall'input_hash
ordine di arrivo → esito
```

**Una proprietà che sopravvive alla propria mutazione non è provata**, e la build fallisce.
(L'audit precedente riportava *una* mutazione che uccideva *un* test su 27, e la presentava come
prova di qualità: è il segnale minimo, non una dimostrazione.)

### 5.2 Le mutazioni per *omissione* e per *rappresentazione*

I due buchi veri non erano valori sbagliati:
- uno era un'**assenza** (simbolo non legato → contratto sempre soddisfatto);
- l'altro era una **rappresentazione** (espansione binaria del float invece delle cifre).

I property test che variano i valori non li vedono. Servono generatori che tolgono campi e che
scelgono valori non rappresentabili in binario.

### 5.3 Due suite separate

```
CompatibilitySuite   conserva il comportamento dove la specifica non cambia
CorrectnessSuite     impone gli invarianti, anche quando l'uscita deve cambiare
```

Una correzione di sicurezza non può fallire perché non riproduce il comportamento vulnerabile.

---

## 6. Postura di sicurezza

- **Enumerare ogni percorso che può produrre un `Permit`** e testare che ciascuno stato non
  verificato (`missing_binding`, `invalid_context`, `indeterminate`, `timeout`) non ci arrivi
  mai. Oggi è vero; va reso un test che elenca gli stati e fallisce se ne compare uno nuovo non
  classificato.
- **Ricontrollo atomico delle precondizioni** al momento dell'uso: altrimenti resta una corsa
  fra controllo e uso.
- **Chiavi**: identità persistente e storico delle pubbliche ci sono. Mancano politica di
  rotazione scritta e un modello di minaccia di una pagina (chi può firmare, cosa succede se una
  privata è compromessa, chi revoca).
- **Verificabilità di terze parti**: un certificato dev'essere verificabile da chi ha solo il
  materiale pubblico, con un comando. È anche la demo di vendita.
- **`canonical_json`**: suite differenziale Python/Rust/TypeScript su numeri, Unicode, `null`,
  ordinamento — e versione della canonicalizzazione dentro il certificato.

---

## 7. Debiti architetturali da pagare (piccoli, ma sporcano)

| Difetto | Correzione |
|---|---|
| `proof_constraints` contiene prosa formattata | i vincoli reali, o il campo si chiama diversamente |
| `negotiate()`: prezzo 0 → `inf` → l'agente gratuito vince sempre; `estimated_quality` calcolata e ignorata | ranking esplicito, o togliere il campo |
| README dichiara un replay buffer «selettivo» che è FIFO | correggere il codice o la frase |
| PRISM restituisce dict non tipizzati | adapter al confine: *parse, don't validate* |
| `cascade/` non è un repository git | git, licenza, CHANGELOG — mezz'ora, sblocca tutto il resto |

---

## 8. La portata del claim — quali componenti ne fanno parte

**Corretto dalla rev. 1**, dove avevo scritto «taglierei L2, L3, marketplace». Quali prodotti
tenere è una decisione tua, non di chi revisiona. Il fatto tecnico che mi compete è più stretto,
e più utile:

> Nessuno fra L2 (memoria continua EWC), L3 (world model JEPA) e il marketplace A2A può
> contribuire all'affermazione che stai misurando, né influenzarla, né essere validato da essa.

Quindi **restano fuori dal perimetro di questo run** — il che non dice niente sul loro futuro,
solo che non entrano nei dati né nel rapporto. Se restano nel processo che gira durante le
misure, diventano una covariata non registrata, ed è l'unico caso in cui la loro presenza
diventa un problema mio e non tuo.

La regola operativa che ne segue è quella che hai già chiamato bene: **un solo claim alla volta.**
Tutto ciò che non serve a quella frase non viene tagliato — viene *messo dopo*.

---

## 9. La sequenza, con la definizione di «fatto»

**Ordine corretto nella rev. 2:** la pre-registrazione va **per prima**, non quinta. Se il
criterio si scrive dopo aver costruito il banco, il banco finisce per essere costruito attorno al
numero che si spera di ottenere. Scritto prima, è il banco a doversi piegare al criterio.

| # | Lavoro | Fatto quando |
|---|---|---|
| 1 | **Pre-registrazione** + analisi di potenza (n=120, ≥30 nella classe rara) | file committato, criterio e baseline B0/B1/B2 congelati |
| 2 | git + licenza + CI (mypy strict, pytest, gate di mutazione) | la build fallisce se una proprietà sopravvive alla sua mutazione |
| 3 | Banco a verifica di cifre (§1.2.1): il claim nasce dal modello | esiste ≥1 record `approved=True ∧ outcome=False`; nessun `float()` sul percorso del valore |
| 4 | Tre fasce di difficoltà (§1.3) | il tasso di successo **differisce** per fascia, misurato |
| 5 | Telemetria d'ambiente per record (§3.2) + floor VRAM | un cambio di `model_id` a metà run è visibile e segmenta i dati |
| 6 | Propensione vera sulla scelta reale (§2.2) | il campo riflette la politica che ha scelto, o vale 1.0 e lo dichiara |
| 7 | Pilota da 20 | i tre controlli meccanici passano; **nessun AUC viene letto** |
| 8 | Il run | 120 decisioni valide, ≥30 della classe rara, `model_id` stabile |
| 9 | Curva: calibrazione **e** discriminazione, contro B0/B1/B2 | pubblicata qualunque sia il risultato |

**Tempo realistico, part-time e da solo: 3-5 settimane.** La maggior parte non è codice: è il
punto 3 (costruire compiti con un oracolo vero) e il punto 6 (far girare senza contaminazioni).

---

## 10. Le tre cose che un'organizzazione aggiungerebbe, e che puoi imitare da solo

1. **Pre-registrazione.** Sostituisce il revisore indipendente: se il criterio è scritto prima,
   non puoi raccontarti il risultato dopo.
2. **Una seconda paia di occhi che esegue, non che legge.** In questa sessione i difetti veri
   sono usciti tutti eseguendo — il guard, la barriera, il banco. Qualunque revisione che si
   ferma a leggere il codice li avrebbe mancati tutti e tre.
3. **Un solo claim per volta.** Un laboratorio taglia lo scopo finché resta **una** affermazione
   misurabile. La tua è: *«su questo schema, la confidenza dichiarata predice il successo con
   AUC X ± Y ed è calibrata entro Z»*. Tutto ciò che non serve a quella frase, aspetta.

---

## In una riga

Il codice è più sano di quanto il progetto sembri, e il progetto è più lontano di quanto i
numeri sembrino. Manca **un banco che possa fallire in modo informativo** — e finché il
fallimento viene da un dado invece che dal compito, nessun run, per quanto lungo, produrrà la
frase che stai cercando.
