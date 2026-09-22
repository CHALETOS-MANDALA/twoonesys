# CASCADE — audit finale

**Percorso:** `C:\Users\andre\Documents\New OpenCode Project\cascade`
**Data:** 2026-09-17
**Copertura:** tutti i 14 moduli sorgente letti, 11 file di test letti, motore causale e guard Z3
**eseguiti**. Non eseguiti: pipeline, world model e memoria continua (richiedono torch, non
installato qui) — segnati `NON ESEGUITO`.

Etichette: `LETTO` · `ESEGUITO` (ho eseguito e riporto l'output) · `NON ESEGUITO`.

---

## 0. La domanda: CASCADE è un System One?

**Risposta precisa: sì per il 70%, e il 30% che manca è quello che dà il nome alla categoria.**

Nella risposta precedente ho detto "architetturalmente sì, sostanzialmente no" e ho elencato tre
mancanze: calibrazione, percezione, generalità. Dopo aver letto tutto, **una delle tre era
sbagliata** e va corretta.

| Requisito System One | CASCADE | Verdetto |
|---|---|---|
| input strutturato → decisione tipizzata | `CascadePipeline.run(Task, [AgentSignal], state) -> Decision` | **sì** |
| nessuna generazione autoregressiva nel percorso | `run()` non chiama mai un LLM | **sì** |
| uscita tipizzata, mai prosa | `Decision` con campi chiusi | **sì** |
| astensione esplicita | `abstained` + `abstain_reason` + certificato emesso comunque | **sì** |
| soglie che decidono esegui/escala | `confidence_threshold`, `risk_threshold`, `max_ood` | **sì** |
| primitiva Noul (bool come probabilità) | `posterior("incidente") -> {True: p, False: 1-p}` | **sì** |
| legge input non strutturato | `eni_brain.py` — **esiste** (correzione, §1) | **sì, ma rotto** |
| **probabilità calibrata** | **assente** (§2) | **no** |
| decisione dichiarata a schema, generale | cablata in `run()` | **no** |

**La correzione:** avevo detto *"CASCADE non sa leggere, parte da input già strutturato"*.
Falso. `eni_brain.py` è esattamente il ponte percettivo: prende un problema in linguaggio
naturale, interroga ENI, e ne ricava un `AgentSignal` con azione e confidenza. Il percorso
c'è. **Il problema non è che manca: è come è fatto** (§1).

---

## 1. Il ponte percettivo esiste, ed è il punto più debole `LETTO`

`eni_brain.py:36-41, 98-107`:

```python
def _extract_number(text: str) -> Optional[float]:
    m = re.search(r"[-+]?\d*\.?\d+", text or "")     # il PRIMO numero nel testo
    ...
extra = _extract_number(dec.get("rationale", ""))     # rationale = PROSA di un LLM
action = extra if extra is not None else default_action

conf_dec = dec["confidence"]                          # confidenza AUTO-DICHIARATA dall'LLM
conf_fc  = fc["acceptance_probability"] / 100.0
confidence = 0.6 * conf_dec + 0.4 * conf_fc           # pesi arbitrari, mai misurati
```

Tre problemi, in ordine di gravità:

1. **L'azione di controllo viene estratta con una regex dalla prosa di un modello.** Con la
   rationale finta dei test (*"azione di controllo 2.5 con verifica incrementale"*) funziona. Con
   *"In 2 casi su 3 consiglio azione 2.5"* estrae **2**. È precisamente il pattern che tutto il
   resto del tuo ecosistema — la barriera di `evidenza`, il confine claim/evidenza di SIX-IDE —
   esiste per impedire, e qui alimenta direttamente un attuatore.
2. **La confidenza è quella che il modello dichiara di sé**, combinata con pesi `0.6/0.4` scelti
   a mano e mai validati. Entra nel gate come se fosse una probabilità.
3. `manifest()` chiama `generate_keypair()` e **butta via la chiave privata** (`_, pub = …`):
   ENI viene registrato con una chiave pubblica di cui nessuno ha la privata, quindi **non potrà
   mai firmare nulla**. Bug reale, silenzioso.

Il ponte va rifatto con lo stesso principio del resto: il modello **propone da un enum chiuso**
o compila uno **schema tipizzato**, mai produce prosa da cui si estrae un numero.

---

## 2. Quello che manca davvero: zero calibrazione `ESEGUITO`

```
$ grep -ri "calibrat|brier|reliability|ece" cascade/*.py cascade/tests/*.py
(nessun risultato)
```

Nessuna occorrenza in tutto il progetto. E il punto di ingresso è una riga sola:

```python
# pipeline.py:329
confidence = float(winner.confidence)
```

La confidenza che governa il guard, il certificato e il gate è **quella che l'agente dichiara di
sé**. Nessuno ha mai verificato se 0.96 corrisponda al 96%. È l'unica proprietà che definisce un
System One — *"calibrated probabilities"* — e nel codice non c'è.

**Da essere giusti con CASCADE:** il progetto misura parecchio, solo non questo. `benchmarks.py`
calcola `missed_block_rate` e `false_block_rate` per la sicurezza, e l'errore contro la
soluzione analitica per la causale. C'è persino `data_loader.data_split()`. La disciplina della
misura c'è: è puntata sulla correttezza della matematica e sulla sicurezza, non sull'onestà del
numero di confidenza.

---

## 3. Il motore causale è vero — verificato `ESEGUITO`

Non mi sono fidato del README. Ho costruito un modello con un **confonditore** (stagione →
sprinkler, stagione → pioggia) per vedere se `do()` fa davvero la mutilazione del grafo o se è
un `posterior()` travestito:

```
P(pioggia | sprinkler=True)     = 0.1778   ← osservazione, contaminata dal confonditore
P(pioggia | do(sprinkler=True)) = 0.4500   ← intervento
P(pioggia) marginale            = 0.4500   ← il prior: coincide esattamente
=> do() ha tagliato il confondimento
```

**È Pearl fatto correttamente.** L'intervento recide gli archi entranti e riporta la variabile al
suo prior, mentre l'osservazione resta contaminata. Sui tre livelli: inferenza, intervento e
controfattuale a 3 passi funzionano tutti, e il controfattuale restituisce una distribuzione
normalizzata.

**Il limite, misurato:**

```
 6 nodi esogeni binari ->    0.6 ms   (2^6  =   64 assegnazioni)
10 nodi esogeni binari ->   14.2 ms   (2^10 = 1024)
13 nodi esogeni binari ->  138.4 ms   (2^13 = 8192)
```

Enumerazione completa, esatta ed esponenziale. **Il tetto pratico è 10-13 variabili binarie** se
il budget è 150 ms. Va benissimo per una policy di sicurezza o un modello di rischio; è
inutilizzabile su un dominio aperto. Il README non lo dice.

E una assunzione non dichiarata: i nodi esogeni senza CPD ricevono un **prior uniforme**
(`prob *= 1.0 / len(node.values)`, `causal_engine.py:168`). È una scelta di modellazione
nascosta in una riga di implementazione.

---

## 4. Il guard Z3: due fail-open, uno mio `ESEGUITO`

**(a) Quello originale** — un simbolo non legato rende il contratto sempre soddisfatto:

```
medical_guard(), paziente allergico, campo 'allergia' presente  -> (None, False)   bloccato
medical_guard(), STESSO paziente, campo 'allergia' dimenticato  -> ({'dose':400}, True)  APPROVATO
```

**(b) Quello introdotto dalla mia correzione** — premesse contraddittorie, prova vacua:

```
velocita=30 ∧ velocita=90, limite=50
   mia correzione (premesse ∧ ¬regole → unsat):  APPROVA
   protocollo a 3 passi:                          INVALID_CONTEXT
```

Protocollo corretto: validare i binding → **verificare la consistenza delle premesse** (`unsat` →
`invalid_context`, `unknown` → `indeterminate`) → cercare la violazione. `missing_binding`,
`timeout` e `unknown` non diventano mai un permesso.

**Perché 59 test non l'hanno visto:** ogni test del guard, incluso il file property-based che
dichiara di voler *falsificare* il sistema con Hypothesis, **lega sempre tutti i simboli**. La
suite esplora lo spazio dei **valori**; i due buchi stanno nello spazio dei **legami** e delle
**premesse**. Un property test sui valori non può vedere un fail-open causato da un'assenza.

---

## 5. Il protocollo A2A è la parte meglio scritta del progetto `LETTO`

Va detto, perché è l'unico posto dell'ecosistema con questo livello di cura sulla sicurezza:

- `SignedEnvelope` firma **insieme** agent_id, nonce, timestamp e payload — non solo il payload;
- **TTL verificato DOPO la firma**, perché i metadati devono essere autenticati prima di essere
  creduti (commento esplicito nel codice);
- validazione di forma e dimensione **prima** di qualunque lavoro crittografico, anti-DoS;
- `InMemoryNonceStore.claim()` è **atomico sotto lock**, con eviction deterministica (TTL, poi il
  più vecchio) — mai `pop(next(iter(...)))`;
- binding dell'attore: la chiave usata deve appartenere all'agente dichiarato;
- **il limite multi-worker è documentato nella docstring**, non scoperto dopo.

Due difetti residui:

- `negotiate()` ordina per `reputation / price`, e per `price == 0` usa `float("inf")`: **un
  agente gratuito vince sempre, anche con reputazione zero.** La `estimated_quality` viene
  calcolata e poi usata solo come filtro, mai nel ranking — mentre il commento sopra dichiara
  *"score = qualità/(costo relativo al budget) + reputazione"*. Codice e commento divergono.
- **Correzione a quanto avevo detto prima:** avevo scritto che il fallback `pool = affordable or
  bids` perde il filtro di budget. **Falso**: `registry.discover()` filtra già
  `cost_per_call <= max_cost` a monte. Il fallback perde solo il filtro di *qualità*. Errore mio.

---

## 6. Il certificato: giusto come idea, tre difetti di sostanza `LETTO`

`DecisionCertificate` ha la forma corretta — `input_hash`, `policy_version`, `model_versions`,
`solver_status`, `proof_constraints`, `uncertainty_bounds`, TTL, firma Ed25519, `payload()` che
esclude la firma. La docstring centra il punto: *"senza questo, un incidente è archeologia"*.

1. **`solver_status = "sat" if decision.approved else "blocked"`** (`pipeline.py:229`): non viene
   dal solver, viene dal flag di approvazione. Un claim senza evidenza **dentro l'artefatto che
   esiste per essere evidenza**.
2. **`input_hash` non include lo stato**: è calcolato su `state_in: getattr(decision,"_state",None)`
   e `_state` non viene mai assegnato (verificato con grep: nessuna scrittura) → sempre `None`.
   Due decisioni da stati diversi hanno lo stesso hash.
3. **Chiave rigenerata a ogni avvio** (`generate_keypair()` in `__init__`): un certificato non è
   verificabile dopo un riavvio del processo. I test lo mascherano perché verificano nello stesso
   processo che ha firmato.

E `proof_constraints` contiene stringhe formattate (`"P(incidente)=0.317"`), non i vincoli Z3: è
una nota leggibile, non una prova.

---

## 7. La memoria continua non fa quello che dichiara `LETTO`

Il README: *"Replay buffer selettivo (capacity-aware), non 'primo campione del batch'"*.

Il codice (`continuous_memory.py:264-265`): `self.replay.add(x[0], y[0])` — **il primo campione
del batch**. E `SelectiveReplayBuffer.scores` viene scritto solo in `add()` con `1.0` costante e
mai aggiornato, quindi `min(range(n), key=…)` in `_prune` restituisce sempre l'indice 0:
l'eviction è **FIFO**, e `sample()` pesa uniformemente.

Il fix EWC invece è reale: la Fisher viene calcolata a fine task e accumulata (`snapshot_task`),
non ricalcolata sul task corrente.

---

## 8. Riepilogo operativo

### Da prendere, quasi così com'è

| Componente | Perché |
|---|---|
| `a2a_protocol` — `SignedEnvelope`, `NonceStore`, `sign/verify_bytes` | miglior codice di sicurezza del tuo ecosistema |
| `causal_engine` | Pearl corretto, **verificato eseguendo**; tetto 10-13 variabili |
| `DecisionCertificate` (forma) | l'artefatto di audit giusto, con 3 correzioni |
| `canonical_json` / `sha256_hex` | corretti, ma servono test differenziali cross-linguaggio |
| disciplina di `benchmarks.py` | misura tassi reali, non "il test passa" |

### Da correggere prima di usare

| # | Difetto | Gravità |
|---|---|---|
| 1 | guard Z3: simbolo non legato → approva | **critico** |
| 2 | guard Z3: premesse contraddittorie → prova vacua | **critico** |
| 3 | `eni_brain`: azione estratta con regex dalla prosa di un LLM | **critico** |
| 4 | confidenza auto-dichiarata usata come probabilità | **critico** |
| 5 | `solver_status` fabbricato dal flag di approvazione | alto |
| 6 | `input_hash` senza lo stato | alto |
| 7 | chiave di firma rigenerata a ogni avvio | alto |
| 8 | `manifest()` scarta la chiave privata → ENI non può firmare | medio |
| 9 | `negotiate`: prezzo 0 → `inf` → vince sempre | medio |
| 10 | replay buffer FIFO invece che selettivo | basso |

### Da lasciare fuori dalla v1

World model JEPA e memoria continua: richiedono uno stato del mondo da predire, che LBP+2 non ha.
Marketplace A2A (registry, reputazione, FastAPI): è un orchestratore.

---

## 9. La frase finale

CASCADE è **la cosa più vicina a un System One che esista nel tuo PC**, e la distanza che resta
non è architettura: è **una misura**. La forma c'è tutta — decisione tipizzata, nessun decoder,
astensione, soglie, certificato. Manca il gesto che rende vero il numero che quella forma
trasporta, e manca in senso letterale: la parola "calibrazione" non compare in nessuno dei 14
moduli.

Il che vuol dire che il pezzo mancante non è un anno di lavoro. È un modulo da centoventi righe,
più la disciplina di registrare gli esiti — e la disciplina, guardando `a2a_protocol.py` e
`benchmarks.py`, ce l'hai già dimostrata altrove.
