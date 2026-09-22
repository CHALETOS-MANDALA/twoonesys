# CASCADE - CTO Completion Plan

Data: 2026-09-17
Owner: CTO / Principal Backend Engineer
Repository: C:\Users\andre\Documents\New OpenCode Project\cascade

## Missione

Portare CASCADE da harness operativo verificato a prodotto/runtime System One adottabile per agenti che devono agire nel mondo reale.

La definizione del prodotto e':

CASCADE riceve una proposta da Latent Brain+, Jev, Ollama o altro modello; separa proposta, evidenza, autorizzazione ed esecuzione; rifiuta cio' che non e' verificabile; esegue solo azioni consentite; osserva l'esito; conserva la traccia; usa gli esiti per misurare e migliorare il routing.

## Stato verificato

### Verde

- Suite CASCADE: 323 test passati.
- Python/Torch/CUDA disponibili sul PC.
- PRISM collegato come worker residente.
- CalcKernel collegato e verificato.
- KIARNEL raggiungibile su 127.0.0.1:8023.
- Worker KIARNEL autenticato e provato su path autorizzato.
- Ollama reale collegato.
- Fallback reale Qwen -> DeepSeek provato.
- Latent Brain+/SIFT collegato tramite `latent_bridge.py`.
- Memoria LBP persistente provata.
- Azione filesystem reale provata.
- HTTP 200, 503, timeout e HTTPS provati.
- Restart e replay dei log provati.
- Identita' di firma persistente e KeyRegistry presenti.
- Claim Barrier usa Decimal/stringhe, controllo segno e zeri impliciti.
- `selection_probability`, `contract_digest`, `label_source` persistiti.
- Mutation test della barriera rilevato.

### In corso

Campagna LBP reale:

- script: `cascade/run_lbp_calibration_100.py`
- obiettivo: 100 decisioni
- backend: Latent Brain+/SIFT con cinque esperti Ollama
- modello: `deepseek-r1:7b`
- memoria: `cascade/run/lbp_calibration_100/lbp_memory`
- stato osservato al momento della consegna: 15/100 record persistiti
- processo in esecuzione: non interrompere senza verificare il terminale proprietario

### Non ancora dimostrato

- calibrazione definitiva della coerenza LBP su traffico non controllato;
- benchmark indipendente contro Jev sullo stesso dataset e hardware;
- throughput concorrente e recovery da crash in produzione;
- controllo dei singoli esperti interni di un GGUF MoE reale;
- deploy SaaS multi-tenant;
- adozione da parte di un operatore esterno all'autore.

## Architettura target

```text
Client / Agent / API
        |
        v
Latent Brain+ / Jev / Ollama
        |
        v
CASCADE Decision Gateway
        |
        +--> Proposal Contract
        +--> Semantic Context / Memory
        +--> PRISM Evidence Selection
        +--> CalcKernel Deterministic Evidence
        +--> KIARNEL Operational Verification
        +--> Policy and Guard
        +--> Permit / Grant / TOCTOU
        +--> Executor Adapter
        +--> Outcome Log
        +--> Calibration and Model Router
        |
        v
World: filesystem, HTTP, database, code workspace, service
        |
        v
Observed Outcome -> label -> calibration -> memory
```

## Contratti obbligatori

### Proposal

Ogni modello deve produrre una proposta tipizzata, non un'autorizzazione implicita.

Campi minimi:

- `request_id`
- `agent_id`
- `proposal`
- `confidence`
- `confidence_kind`
- `model_version`
- `prompt_hash`
- `created_at`

`confidence_kind` deve distinguere almeno:

- `raw_uncalibrated`
- `coherence_uncalibrated`
- `calibrated`
- `missing`

### Evidence

Ogni evidenza deve contenere:

- `tool`
- `args`
- `exit_code`
- `stdout_hash`
- `parsed`
- `timestamp`
- `contract_digest`
- `verifier_version`

Regola: nessuna evidenza significa nessun claim positivo.

### Authorization

Un permit deve essere limitato a:

- azione;
- scope;
- parametri;
- soggetto;
- scadenza;
- precondizioni;
- grant one-shot;
- digest degli argomenti.

Regola: proposta, evidenza o probabilita' non sono permessi.

### Execution

Gli unici esiti ammessi sono:

- `Succeeded`;
- `Failed`;
- `Indeterminate`.

`Indeterminate` e' obbligatorio quando il processo non sa se l'azione sia avvenuta. Non deve diventare automaticamente successo o fallimento.

### Outcome

Ogni decisione deve registrare al momento della scelta:

- `raw_confidence`;
- `measured_p` se disponibile, altrimenti `null`;
- `selection_probability` in `(0,1]`;
- `contract_digest`;
- `label_source` da insieme chiuso;
- `approved`;
- `outcome`;
- `touched`;
- `model_version`;
- `policy_version`;
- `request_id`.

## Piano di completamento ordinato

### P0 - Finire la campagna LBP reale

1. Lasciare completare il processo attuale.
2. Verificare che il log abbia esattamente 100 record.
3. Verificare `settled=100`.
4. Verificare `with_propensity=100`.
5. Verificare `with_label_source=100`.
6. Verificare almeno un successo e un fallimento.
7. Verificare che la memoria LBP contenga gli episodi.
8. Riavviare il lettore del log e confrontare le metriche.
9. Calcolare ECE raw, ECE calibrato, Brier e success rate.
10. Non chiamare questi numeri calibrazione definitiva se il traffico e' ancora sperimentale.

Comandi:

```powershell
cd "C:\Users\andre\Documents\New OpenCode Project"
$py="C:\Users\andre\Documents\New OpenCode Project\sift-framework\.venv\Scripts\python.exe"
$env:PYTHONPATH="C:\Users\andre\Documents\New OpenCode Project"
$env:CASCADE_PRISM_PATH="C:\Users\andre\Documents\New OpenCode Project\WFT-IA"

& $py -c "from cascade.outcome_log import OutcomeLog; p='cascade/run/lbp_calibration_100/outcomes.jsonl'; l=OutcomeLog(p).load(); print(l.metrics())"
```

### P0 - Chiudere la prova mutazione completa

Usare una copia temporanea, mai il file di produzione.

Mutazioni minime da applicare una per volta:

1. reintrodurre `float()` nella barriera;
2. rimuovere gli zeri impliciti;
3. accettare segno discordante;
4. accettare `selection_probability=0`;
5. omettere `key_id` dal certificato;
6. sostituire `solver_status` con il flag `approved`;
7. togliere lo stato dall'hash;
8. far derivare l'azione dalla prosa.

Criterio:

- ogni mutazione di sicurezza deve essere uccisa dai test;
- se una mutazione sopravvive, aggiungere un test prima di dichiarare verde.

### P0 - Chiudere i rischi tecnici residui

#### Azione tipizzata

Mantenere l'azione solo in campi strutturati. Mai estrarre numeri dalla rationale con regex.

Se il campo manca:

- usare solo un default esplicito dichiarato dal chiamante;
- altrimenti `ProposalUnavailable`;
- loggare `action_source`.

#### Certificato

Il certificato deve contenere:

- `solver_status` reale;
- `state_in` nell'`input_hash`;
- rumore e contesto nell'`input_hash`;
- `key_id`;
- policy version;
- model versions;
- expiry;
- signature.

#### Identita'

- chiavi persistenti;
- storico delle chiavi pubbliche;
- sconosciuto = non verificabile;
- chiave privata mai nel repository;
- rotazione senza invalidare il passato.

### P1 - Calibrazione statistica seria

Dopo il primo campione da 100:

1. separare train/calibration/test;
2. non usare gli stessi esiti per fit e valutazione finale;
3. calcolare ECE, Brier e reliability diagram;
4. calcolare metriche per modello;
5. calcolare metriche per dominio;
6. calcolare metriche per tipo di azione;
7. usare `selection_probability` per IPS/off-policy;
8. misurare intervalli di confidenza bootstrap;
9. registrare drift nel tempo;
10. bloccare la parola `calibrato` finche' il test fuori campione non passa.

Criterio minimo iniziale:

- almeno 100 record settled;
- propensione completa;
- label completa;
- almeno due classi di esito;
- nessuna riga corrotta;
- replay identico dopo restart;
- report riproducibile da un comando.

### P1 - Benchmark competitivo

Costruire uno stesso dataset di richieste e confrontare:

- CASCADE + DeepSeek;
- CASCADE + Qwen;
- CASCADE + Latent Brain+;
- Jev, se disponibile;
- modello diretto senza harness;
- harness senza PRISM;
- harness senza KIARNEL;
- harness senza memoria.

Metriche:

- latenza p50/p95/p99;
- costo per decisione;
- token;
- VRAM;
- success rate;
- failed rate;
- indeterminate rate;
- fallback rate;
- ECE;
- Brier;
- false approval rate;
- false block rate;
- azioni duplicate;
- audit completeness.

Regola: stesso hardware, stesso modello, stesso prompt, stesso numero massimo di token, stesso dataset, stesso timeout.

### P1 - Concorrenza e crash recovery

Implementare test reali per:

- 10, 50 e 100 richieste simultanee;
- due richieste con lo stesso grant;
- crash prima dell'executor;
- crash dopo l'executor prima del log;
- timeout dopo possibile commit remoto;
- doppio restart;
- log parzialmente scritto;
- due processi sullo stesso log.

Criteri:

- nessun doppio grant;
- nessun falso successo;
- nessuna perdita silenziosa;
- `Indeterminate` quando lo stato non e' ricostruibile;
- riconciliazione esplicita.

### P1 - Expert/VRAM runtime

Il modulo attuale gestisce artefatti e tensor CUDA reali. Per il runtime MoE completo serve:

1. leggere manifest GGUF;
2. identificare tensor e layer degli esperti;
3. calcolare costo memoria per expert;
4. prevedere il routing;
5. prefetch;
6. eviction;
7. dispatch nel runtime;
8. osservare gli esperti usati davvero;
9. confrontare predizione e uso effettivo;
10. misurare latenza di load e cache hit.

Non dichiarare controllo degli esperti interni finche' CASCADE non e' collegato a un runtime GGUF reale.

### P1 - Production hardening

- packaging installabile;
- configurazione validata;
- secrets manager;
- TLS/mTLS per servizi;
- audit append-only firmato;
- retention policy;
- backup e restore;
- health/readiness/liveness;
- metrics Prometheus/OpenTelemetry;
- rate limiting;
- multi-tenant isolation;
- RBAC;
- idempotency key;
- schema migration;
- compatibilita' Windows/Linux;
- SBOM e dependency audit;
- vulnerability scanning;
- disaster recovery test.

### P2 - Productizzazione SaaS

API minime:

```text
POST /v1/decisions
POST /v1/proposals
POST /v1/outcomes
GET  /v1/decisions/{id}
GET  /v1/certificates/{id}
GET  /v1/metrics/calibration
GET  /v1/health
```

Ogni response deve contenere:

- `decision_id`;
- stato tipizzato;
- modello e versione;
- policy e versione;
- evidenza/certificate reference;
- outcome reference;
- latenza;
- correlation id.

Non esporre il modello come autorita' diretta: tutto deve passare dal decision gateway.

## Definition of Done

CASCADE puo' essere dichiarato prodotto operativo quando tutti i punti sono veri:

- [ ] 100+ decisioni LBP reali settled;
- [ ] 100+ propensioni persistite al momento della scelta;
- [ ] successi e fallimenti reali;
- [ ] replay identico dopo restart;
- [ ] ECE/Brier fuori campione;
- [ ] mutation suite completa;
- [ ] KIARNEL live con auth e policy path;
- [ ] PRISM live;
- [ ] CalcKernel live;
- [ ] Latent Brain+ live;
- [ ] benchmark contro baseline;
- [ ] test concorrenza;
- [ ] test crash recovery;
- [ ] test sicurezza;
- [ ] packaging riproducibile;
- [ ] documentazione operativa;
- [ ] seconda persona riesce a installare ed eseguire;
- [ ] almeno un workflow esterno ripetuto con esito verificabile.

## Posizionamento finale

La frase corretta per il prodotto e':

> CASCADE e' un harness System One operativo per agenti: non sostituisce il modello, ma controlla il percorso tra proposta e mondo reale. Coordina modelli e memoria, verifica evidenza con PRISM e CalcKernel, usa KIARNEL per la verifica operativa, autorizza azioni limitate, persiste gli esiti e misura la propria affidabilita'.

Non dichiarare ancora:

- production-ready generale;
- calibrazione definitiva;
- controllo completo degli esperti MoE;
- superiorita' quantitativa rispetto a Jev;
- IP non replicabile;
- adozione di mercato.

Queste dichiarazioni diventano lecite solo dopo i benchmark e i criteri di accettazione sopra elencati.

## Risposta breve a una revisione critica

CASCADE non deve essere difeso dicendo che e' perfetto. Deve essere difeso mostrando il confine tra cio' che e' misurato e cio' che e' ancora un obiettivo.

Oggi e' gia' un harness operativo reale, con integrazioni live e azioni verificate. Il lavoro rimanente non e' dimostrare che il codice esiste: e' trasformare l'integrazione in dati fuori campione, benchmark comparabili, recovery sotto guasto e adozione indipendente.

Il prossimo numero che conta e':

```text
100+ decisioni generate da LBP+
100+ propensioni registrate
esiti reali variati
ECE/Brier fuori campione
replay identico
```
