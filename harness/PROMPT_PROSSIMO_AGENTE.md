# Briefing per il prossimo agente — progetto CASCADE / System One

Incolla questo come primo messaggio. È scritto per essere letto a freddo, senza contesto
precedente.

---

## 0. Come si lavora qui (non negoziabile)

Lavori con Rubinho, sviluppatore indipendente. Si parla **italiano**.

Cinque regole. La prima è quella che conta più di tutte:

1. **Non dichiarare mai niente che non hai misurato.** Se hai letto il codice, dillo. Se l'hai
   eseguito, mostra l'output. «Implementato» non vuol dire «funziona». Usa etichette esplicite:
   `LETTO` / `ESEGUITO` / `RIPORTATO` / `NON VERIFICATO`.
2. **La suite verde non prova niente.** In questo progetto due fail-open silenziosi sono
   sopravvissuti a una suite completamente verde (§3). Quando verifichi, scrivi i casi
   avversariali tu, non fidarti dei test esistenti.
3. **Niente stub, mock o placeholder** nel codice consegnato. Se non si può fare davvero, si
   dice che non si può.
4. **I test non si aggirano.** Non si cancella un test per farlo passare. Se un test cade,
   o è il codice a essere sbagliato, o è il test — e va deciso con una prova, non con una
   preferenza. Un test che difende un comportamento *vulnerabile* va sostituito, dichiarandolo.
5. **Lavora end-to-end e decidi da senior dev.** Non fermarti a chiedere conferma a ogni passo.
   Se sbagli, ammettilo subito e mostra la prova dell'errore.

Rubinho verifica. Ha già smentito affermazioni sbagliate fatte da agenti precedenti, me
compreso. Aspettati che ti controlli, e rendigli il controllo facile.

---

## 1. La tesi del progetto

**TypeSafe AI** ha pubblicato (16 settembre 2026) **Jev**, primo «System One model»: input
strutturato → decisione tipizzata + probabilità calibrata, **senza generare testo**. Tre
primitive soltanto: `Choice` (categorica, cardinalità ≤255), `Score` (numerico in intervallo),
`Noul` (booleano come probabilità). Addestrato con RLCD (RL for Calibrated Decisions). Numeri
dichiarati dal fornitore: 40-200× più veloce, 70-500 ms. Limiti dichiarati da loro: non genera
stringhe, niente immagini, peggiore degli LLM sui compiti ad alto ragionamento.

Rubinho era arrivato alla stessa idea mesi prima, da solo. **Ma il suo non è un modello: è un
harness.** È la differenza che regge tutto il progetto:

```
Jev       = un modello che devi adottare
CASCADE   = uno strato che si applica ai modelli che già usi — incluso Jev
```

Formulazione corretta, sua e da usare:

> CASCADE è un **runtime/harness System One**: riceve proposte da modelli o sistemi cognitivi,
> le sottopone a evidenza e policy, autorizza o blocca azioni, osserva l'esito e conserva la
> traccia verificabile.
>
> System One **completo e production-ready generale: no.**
> System One **operativo, circoscritto e verificato: sì.**

L'invariante che tutto il sistema serve — quattro confini che non vanno mai collassati:

```
DATO          DECISIONE        AUTORIZZAZIONE       ESECUZIONE
valido?        corretta?         consentita?          riuscita?
   │               │                   │                  │
Evidence      Assessment        Authorization      ExecutionResult
```

**Una prova non è un permesso. Una probabilità alta non supera un divieto. Un timeout non
dimostra un fallimento.**

---

## 2. La mappa dei componenti

| Componente | Percorso | Ruolo | Stato |
|---|---|---|---|
| **CASCADE** | `C:\Users\andre\Documents\New OpenCode Project\cascade` | l'harness. È qui che si lavora | attivo |
| **LATENT_BRAIN_PLUS** | `…\Desktop\_MADRE_RUBINHO\01_PROGETTI\SIX_MADRE\02_LATENT_BRAIN_MEMORY\LATENT_BRAIN_PLUS` | livello cognitivo sopra CASCADE; i documenti di architettura stanno in `docs\` | attivo |
| **SIFT framework** | `New OpenCode Project\sift-framework` | 5 esperti, usato via `latent_bridge.py` | collegato |
| **PRISM** | configurabile con `CASCADE_PRISM_PATH` | pertinenza/geometria, worker `prism.relevance` | collegato |
| **CalcKernel** (`matematica`) | `C:\Users\andre\Desktop\matematica` | calcolo deterministico a 40 cifre + barriera `evidenza` | collegato via worker |
| **KIARNEL** (crate Rust `grok`) | `…\SIX_MADRE\grok`, servizio su `127.0.0.1:8023` | verifica/azione esterna, worker `kiarnel.verify` | collegato, **FROZEN**: non modificarlo |
| **Ollama** | locale | modelli; router con fallback | attivo |

Documenti da leggere **prima di toccare qualunque cosa**, in quest'ordine:

```
cascade\AUDIT_FINALE_2026-09-17.md              cosa c'era prima
cascade\VERIFICA_INDIPENDENTE_2026-09-18.md     verifica in container pulito
cascade\PATCH_2026-09-18.md                     prima correzione
cascade\PATCH2_2026-09-18.md                    seconda correzione
cascade\REVISIONE_AUDIT_2026-09-18.md           revisione critica dell'audit
LATENT_BRAIN_PLUS\docs\LBP2_CONTRATTI_V1.md     LA SPECIFICA. Qui stanno i contratti
LATENT_BRAIN_PLUS\docs\LBP2_PROBLEMI_E_SOLUZIONI.md   conformal, IPS, le tre matematiche
LATENT_BRAIN_PLUS\docs\LBP2_ARCHITETTURA.md     storia del ragionamento (rev. 1-3 superate in parte)
```

---

## 3. Dove eravamo — due fail-open trovati sotto una suite verde

Questo è il precedente che spiega la regola 2. Entrambi trovati eseguendo, non leggendo.

**(a) Guard Z3 — un simbolo non legato faceva approvare tutto.**
`SymbolicContract.evaluate` trattava `solver.check() == sat` come «vincolo soddisfatto». Ma
`sat` significa «esiste un'assegnazione delle variabili **libere** che rende vera la formula».
Ogni simbolo non fornito nel contesto diventava una via di fuga. Prova reale, con
`medical_guard()`:

```
paziente allergico, campo 'allergia' presente    -> (None, False)        bloccato
STESSO paziente, campo 'allergia' dimenticato    -> ({'dose':400}, True) APPROVATO
```

E la prima correzione (`premesse ∧ ¬regole → unsat`) ne introduceva un altro: con premesse
contraddittorie la formula è insoddisfacibile per vacuità e il guard **approva**. Ora il
protocollo è a tre passi (binding → consistenza delle premesse → ricerca della violazione) in
`guard_protocol.py`, con cinque stati e **solo `RULES_VERIFIED` che autorizza**.

**(b) Barriera dei claim — respingeva il 50% dei claim VERI.**
`_digits_are_prefix` confrontava l'espansione binaria del float:
`float("143.1118")` = `143.11179999999998813109` → troncato a 4 decimali dà `1117`.

```
prima:  claim fedeli respinti  995/2000 = 49.8%
dopo:   claim fedeli respinti    0/2000 =  0.0%
```

Ora passa da `Decimal`, `float()` non compare nel percorso di verifica, il segno è controllato,
e gli zeri impliciti sono cifre (`42.5` == `42.5000`).

**Perché nessuna delle due suite li aveva visti:** i test — incluso un file property-based con
Hypothesis che dichiara di voler *falsificare* il sistema — legavano sempre tutti i simboli ed
esploravano solo lo spazio dei **valori**. I buchi stavano nello spazio dei **legami** e in
quello della **rappresentazione**.

→ **I test di mutazione devono includere l'omissione, non solo il valore sbagliato.**

---

## 4. Dove siamo — stato al 18 settembre 2026

### 4.1 Chiuso e provato

- separazione `Assessment` / `Authorization` / `ExecutionResult`, con `Indeterminate` per la
  risposta persa (un timeout non è un fallimento);
- guard Z3 a tre passi; `missing_binding`, `invalid_context`, `indeterminate` **non** autorizzano mai;
- barriera su claim **strutturati** (`operation, arguments, subject_id, value, unit, precision,
  rounding_mode, evidence_ref`): l'oggetto si distingue per `subject_id`, non contando cifre nel testo;
- `conformal.py`: split conformal corretto, `k = ceil((n+1)(1-α))`, e `k > n → +inf`
  (troppi pochi punti → non respingere mai: degrada verso il conservativo);
- `outcome_log.py` v2 con `selection_probability`, `contract_digest`, `label_source`
  (insieme chiuso `mechanical|human|behavioral`), metriche `with_propensity` / `off_policy_ready`;
- `signing.py`: identità persistente + storico delle chiavi pubbliche → un certificato resta
  verificabile dopo un riavvio e dopo una rotazione; chiave sconosciuta = **non verificabile**;
- `solver_status` nel certificato è **parametro obbligatorio** e viene dal solver reale, non da
  `decision.approved`; `input_hash` include stato e rumore;
- `eni_brain`: l'azione arriva **solo** da un campo tipizzato. Prima veniva estratta con una
  regex dalla prosa del modello (con *«in 2 casi su 3 consiglio azione 2.5»* si otteneva **2**,
  e quel numero andava a un attuatore).

Suite: **~330 test verdi** con torch (verifica il numero, non fidarti di questo).
Prove di mutazione: rimettere `float()` → 12 test cadono; togliere la propensione → 7.

### 4.2 Il run di calibrazione — IN CORSO E ROTTO

`cascade\run\lbp_calibration_100\outcomes.jsonl`, obiettivo 100 decisioni. All'ultimo controllo:
68 record. **Il run si è rotto a metà e va diagnosticato prima di continuare.**

```
record 000–059   60 record,  ZERO fallimenti
record 060–067    8 record,  OTTO fallimenti     ← tutti consecutivi
record 064–067    confidenza inchiodata a 1.0000 ← seconda degradazione
```

Non è un tasso di fallimento: è una rottura intorno a `touched ≈ 1789649650`. Va trovata
la causa (servizio caduto? Ollama? un path?) prima di aggiungere altri record: se il run
arriva a 100 così, i dati sono avvelenati.

**La notizia buona, che i dati grezzi nascondevano.** Sui 63 record sani (esclusa la coda con
confidenza saturata):

```
AUC = 0.852     IC 95% bootstrap = [0.695, 0.970]     (esclude 0.5)

curva di affidabilità:
  conf [0.70, 0.80)   n=16   successi  81%
  conf [0.80, 0.90)   n=21   successi  95%
  conf [0.90, 1.00)   n=26   successi 100%
```

Monotona, direzione giusta. **La coerenza SIFT separa i successi dai fallimenti.** Sui dati
grezzi l'AUC era 0.431 — peggio del caso — e quel numero era prodotto interamente dai record
rotti. È preliminare: con 4 soli fallimenti nel set pulito l'intervallo resta largo.

### 4.3 Tre problemi aperti nel run, da sistemare prima di ripartire

1. **`action` è costante** (`verified_model_action` in tutti e 68). La propensione è registrata
   e **coerente** (0.25 osservata al 25%, 0.75 al 75%, somma 1.0) ma senza l'identità del ramo
   scelto non si può stimare nessuna politica alternativa: IPS/doubly-robust restano inservibili.
   → loggare *quale* braccio è stato scelto.
2. **`approved == outcome` in 68 record su 68.** Zero casi di azione approvata che poi fallisce.
   Se l'`outcome` è *derivato* da `approved` invece che osservato dopo, la calibrazione è
   **circolare**: si misura la confidenza del sistema contro la sua stessa decisione.
   → verificare che la verifica meccanica sia indipendente dal gate che ha approvato.
3. **Numerosità.** Con zero fallimenti nei primi 60 record la classe minoritaria non esiste.
   Servono **25-30 esempi della classe rara**: a un tasso genuino del 12% significa **~238
   decisioni, non 100**. Meglio rendere il compito abbastanza vario da fallire davvero.

---

## 5. Dove vogliamo arrivare

### 5.1 Il traguardo, in un numero

> **La prima curva di affidabilità con varianza vera**: ≥25-30 esiti della classe minoritaria,
> propensione scritta al momento della scelta, ground truth indipendente dall'approvazione, e
> un ECE pubblicato con valutazione **fuori campione**.

Da quel momento «0.90» vuol dire 0.90 ed è una misura, non un'affermazione. È l'unica cosa che
nessuno può contestare, ed è ciò che distingue questo progetto da un README convincente.

### 5.2 Le due metriche, mai una sola

Un predittore che restituisce sempre il tasso base è **perfettamente calibrato e inutile**.
Servono insieme:

- **calibrazione** — il numero dice la verità (ECE, diagramma di affidabilità);
- **discriminazione** — il numero *cambia* con il caso (AUC, cardinalità media dell'insieme conformal).

Con baseline dichiarate **prima** di guardare i risultati: ramo costante (B0), l'euristica
attuale (B1), scelta casuale (B2). Se non batti B1, il progetto non ha pagato su quello schema —
e va detto.

### 5.3 Il KPI è manipolabile: non usarlo da solo

«Frazione di richieste risolte senza generare un token» → un sistema che si astiene sempre
lo risolve al 100%. Va sempre letto con: qualità sui casi accettati automaticamente, copertura
automatica, frequenza delle astensioni, costo e latenza, esiti mancanti, violazioni di policy.

### 5.4 Dopo la curva

1. Secondo schema decisionale **fuori dal retrieval** e con ground truth **meccanico**
   (candidato: `azione.autorizza` → `ALLOW / BLOCK / REVIEW`, verificata da Kiarnel o Z3).
   Serve a dimostrare che non è solo un router della memoria.
2. Pubblicare il pezzo piccolo e indipendente: **la calibrazione conformal su API che non danno
   i logprob** (~120 righe, numpy). Risolve un problema reale di chiunque costruisca agenti.
3. Igiene: `cascade\` **non è un repository git**. Prima di qualunque conversazione esterna
   servono git, licenza dichiarata e proprietà pulita.

---

## 6. Cosa NON fare

- **Niente cervelli nuovi, DB nuovi, orchestratori nuovi, tracing framework nuovi.** Il valore
  sta nel consolidare ciò che esiste.
- **Niente modelli addestrati.** La calibrazione si **misura**, non si addestra: una mappa
  (isotonica/Platt) o conformal danno la stessa garanzia *di gruppo* che RLCD dà a Jev, senza GPU.
- **Kiarnel è FROZEN**: se ne consuma il contratto HTTP, non si modifica.
- **Il CalcKernel non si reimplementa**: si chiama, come fa `evidenza`.
- **Niente generazione mascherata da decisione**: se lo spazio di uscita supera qualche
  centinaio di alternative non stai decidendo, stai generando. Si decompone.
- **Il piano decisionale non importa nulla dal decoder**, mai — regola verificabile in CI.
- **Attenzione a non diventare il progetto 95.** Rubinho ha 94 progetti censiti, quasi nessuno
  collegato agli altri. Lo schema ricorrente non è costruire male: è costruire ottimi pezzi
  isolati. Ogni proposta di «aggiungiamo anche…» va pesata contro questo.

---

## 7. Comandi di verifica

```powershell
cd "C:\Users\andre\Documents\New OpenCode Project"
python -m pytest cascade/tests -q                 # suite completa (serve torch)
python -m pytest cascade/tests -q -k regressioni  # solo le regressioni chiuse

# stato del run di calibrazione
$p = "cascade\run\lbp_calibration_100\outcomes.jsonl"
(Get-Content $p).Count
Get-Content $p -Tail 1
```

Per l'analisi dei log usa Python, non l'occhio: conta la varianza dell'esito, la coerenza tra
propensione dichiarata e frequenza osservata, l'AUC con intervallo di confidenza bootstrap, e
**guarda l'ordine temporale** — è così che si è scoperta la rottura al record 060.

---

## 8. Il primo compito

1. Leggi i documenti elencati in §2.
2. Esegui la suite e riporta il numero reale (non fidarti del «~330»).
3. **Diagnostica la rottura al record 060** del run di calibrazione. È il blocco attuale.
4. Sistema i tre problemi di §4.3 (identità del braccio, indipendenza dell'esito, numerosità).
5. Riparti con il run, e produci la prima curva di affidabilità con calibrazione **e**
   discriminazione, contro le baseline dichiarate prima.

Se durante il lavoro trovi che un'affermazione di questo briefing è sbagliata: **dillo, con la
prova.** È successo più volte, ed è il modo in cui questo progetto è migliorato.
