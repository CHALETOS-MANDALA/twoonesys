# Audit tecnico CASCADE come harness System One

**Data:** 2026-09-17  
**Progetto:** `C:\Users\andre\Documents\New OpenCode Project\cascade`  
**Scopo:** chiarire che cosa è CASCADE, che cosa è stato realmente verificato e perché non è corretto ridurlo a un semplice prototipo o confrontarlo con Jev come se fossero lo stesso oggetto.

---

## 1. Executive summary

CASCADE è un **harness operativo reale con comportamento System One**, non un modello linguistico e non un mock architetturale.

La definizione corretta è:

> CASCADE è un runtime/harness System One che riceve proposte da modelli o sistemi cognitivi, le sottopone a evidenza e policy, autorizza o blocca azioni, osserva l'esito e conserva la traccia verificabile.

CASCADE non è Jev e non pretende di essere un modello addestrato con parametri propri. Il confronto corretto non è:

```text
CASCADE contro Jev come modelli
```

ma:

```text
Jev              = modello decisionale tipizzato
CASCADE          = harness che governa modelli, strumenti e azioni
Latent Brain+    = memoria, esperti e livello cognitivo
PRISM            = pertinenza/selezione dell'evidenza
CalcKernel       = calcolo deterministico
KIARNEL          = verifica/azione operativa esterna
```

La tesi difendibile è quindi:

> Jev riduce il rischio restringendo l'uscita a decisioni tipizzate. CASCADE affronta il rischio sistemico dimostrando che cosa accade tra proposta, evidenza, autorizzazione ed esecuzione.

Sono problemi diversi e complementari.

---

## 2. Che cosa significa "funzionare"

Per CASCADE non basta che un modello produca testo plausibile. Il sistema deve distinguere quattro livelli:

```text
proposta       che cosa suggerisce un modello
 evidenza      che cosa è stato verificato
 autorizzazione che cosa è consentito fare
 esecuzione    che cosa è realmente accaduto
```

Questi livelli non possono essere collassati:

- una risposta plausibile non è evidenza;
- un'evidenza matematica non è un permesso;
- un permesso non è un'esecuzione riuscita;
- un'esecuzione iniziata non è necessariamente un'esecuzione conclusa;
- una confidenza dichiarata non è automaticamente una probabilità calibrata.

Questa separazione è il nucleo di CASCADE.

---

## 3. Architettura realmente presente

Il percorso operativo verificato è:

```text
Latent Brain+ / modello Ollama
              |
              v
          CASCADE
              |
       +------+------+----------------+
       |             |                |
     PRISM       CalcKernel        KIARNEL
       |             |                |
       +------+------+----------------+
              |
       Claim Barrier / policy
              |
       Action Authorize
              |
       filesystem / API / servizio
              |
       outcome log + memoria
```

### 3.1 Latent Brain+

Il bridge in `latent_bridge.py` carica il vero `SIFTFramework` da `sift-framework` e traduce una `SIFTResult` in una proposta CASCADE tipizzata:

- testo prodotto;
- coerenza cross-esperti;
- relevances;
- contributi;
- metadati di memoria;
- latenza;
- tipo di confidenza esplicito: `coherence_uncalibrated`.

Il bridge non dichiara la coerenza SIFT come probabilità calibrata.

### 3.2 PRISM

PRISM è un worker residente CASCADE (`prism.relevance`). Ordina documenti già disponibili in base alla pertinenza. Il backend reale viene caricato dal percorso configurabile `CASCADE_PRISM_PATH`.

### 3.3 CalcKernel

`calc.kernel` esegue il calcolo deterministico e produce evidenza strutturata con:

- parametri;
- risultato numerico;
- hash dell'output macchina;
- valori attesi;
- esito del calcolo.

Per gli artefatti ad alta precisione, i numeri restano stringhe o `Decimal`, non float binari.

### 3.4 KIARNEL

KIARNEL è un servizio operativo separato su `127.0.0.1:8023`. CASCADE ora dispone del worker `kiarnel.verify`, che chiama il contratto reale:

```text
POST /v1/ask
{
  "goal": "...",
  "file": "...",
  "execute": false
}
```

Il worker:

- legge il bearer token dalle variabili configurate o da `%LOCALAPPDATA%\\Kiarnel\\auth.token`;
- accetta solo JSON con `ok == true`;
- tratta `401`, `403`, timeout, risposta vuota e JSON invalido come fallimento;
- non trasforma un rifiuto del servizio in evidenza positiva.

La prova live ha distinto correttamente:

- `401`: autenticazione assente;
- `403 KIARNEL_PATH_DENIED`: autenticazione presente ma path fuori policy;
- `200`/`ok=true`: verifica accettata su un file nella data directory autorizzata.

### 3.5 Claim Barrier

La barriera confronta cifre decimali come cifre, usando `Decimal` e stringhe, non l'espansione binaria di un float.

Sono verificati:

- claim fedele accettato;
- cifra alterata respinta;
- precisione oltre l'evidenza respinta;
- segno discordante respinto;
- zeri impliciti accettati (`42.5 == 42.5000` nel contratto di precisione);
- valori ad alta precisione dichiarati come stringhe o `Decimal`.

### 3.6 Autorizzazione ed esecuzione

CASCADE separa:

- permit;
- grant one-shot;
- controllo dei parametri;
- controllo anti-TOCTOU;
- executor;
- risultato `Succeeded`, `Failed` o `Indeterminate`.

Un errore o una risposta persa non diventa automaticamente un successo.

---

## 4. Prove eseguite sul PC

### 4.1 Suite completa

Ultima esecuzione verificata:

```text
323 passed in 28.30s
```

La suite copre contratti, autorizzazione, guard, causalità, memoria, pipeline, worker, outcome log, certificati e regressioni.

### 4.2 Prova reale modello e fallback

Ollama è stato usato realmente. Una prova ha prodotto:

```text
qwen3.5:27b     -> HTTP 500
fallback        -> deepseek-r1:7b
STATUS          -> succeeded
```

CASCADE ha registrato il fallimento del primo modello e ha usato il fallback operativo.

### 4.3 Prova reale filesystem

Sono stati creati 40 file fisici con il circuito CASCADE. Il log ha registrato 40 esiti e il restart ha ricostruito lo stato con metriche identiche.

### 4.4 Prova reale HTTP

Sono stati verificati:

```text
HTTP 200       -> Succeeded
HTTP 503       -> Failed
Timeout        -> Indeterminate
HTTPS esterno -> Succeeded
```

Dopo restart:

```text
RECORDS_BEFORE=4
RECORDS_AFTER_RESTART=4
METRICS_IDENTICAL=True
OUTCOMES=[True, False, None, True]
```

### 4.5 Catena PRISM + CalcKernel

La catena reale ha prodotto:

```text
docs.retrieve    ok
prism.relevance  ok
calc.kernel      ok
claim.barrier    ok
```

### 4.6 Catena KIARNEL reale

Dopo allineamento del token e uso di un file dentro la data directory autorizzata:

```text
KIARNEL_WORKER=OK
RESPONSE_OK=True
PLANNER=kiarnel-deterministic
```

Catena completa:

```text
docs.retrieve    ok
prism.relevance  ok
calc.kernel      ok
claim.barrier    ok
kiarnel.verify   ok
VERDICT_OK=True
```

### 4.7 Catena Latent Brain+ → CASCADE

Il bridge LBP reale ha usato:

- `SIFTFramework` reale;
- cinque esperti SIFT;
- Ollama `deepseek-r1:7b`;
- memoria LBP persistente;
- feedback utente `0.9`;
- PRISM;
- CalcKernel;
- Claim Barrier;
- azione persistita;
- log CASCADE.

Risultato finale:

```text
MODEL=latent-brain-plus
EVIDENCE=True

docs.retrieve    ok
prism.relevance  ok
calc.kernel      ok
claim.barrier    ok

ACTION=succeeded
```

La memoria LBP ha prodotto artefatti persistenti sotto:

```text
cascade/run/lbp_memory/
```

L'azione e il log sono stati scritti sotto:

```text
cascade/run/lbp_actions/
cascade/run/lbp_cascade.jsonl
```

---

## 5. Calibrazione: ciò che è chiuso e ciò che non lo è

CASCADE ora registra esplicitamente:

```text
selection_probability
contract_digest
label_source
```

`label_source` è vincolato a un insieme chiuso:

```text
mechanical | human | behavioral
```

Le metriche dichiarano se il log è pronto per valutazioni off-policy:

```text
with_propensity
off_policy_ready
```

La confidenza di Latent Brain+ è registrata come:

```text
coherence_uncalibrated
```

Questo è corretto: una coerenza SIFT di `0.86` non significa automaticamente che il sistema abbia successo nell'86% dei casi.

La calibrazione completa richiede:

1. una quantità sufficiente di decisioni;
2. propensione di selezione registrata al momento della scelta;
3. label reali sull'esito;
4. distinzione tra successo, fallimento e indeterminato;
5. valutazione ECE/Brier o equivalente;
6. validazione fuori campione;
7. controllo del drift nel tempo.

Questa non è una debolezza nascosta: è una proprietà che deve essere misurata, non dichiarata.

---

## 6. Mutazione e qualità dei test

La prova di mutazione è stata eseguita su una copia temporanea del codice.

Mutazione applicata:

```python
f_exp.ljust(precision, "0")[:precision]
```

sostituito con:

```python
f_exp[:precision]
```

Risultato:

```text
1 failed, 27 passed
```

Il test caduto è quello che protegge il contratto degli zeri impliciti:

```text
42.5 == 42.5000
```

Questo dimostra che la suite non è solo una collezione di test che passa per caso: rileva una mutazione semantica della barriera.

---

## 7. Confronto corretto con Jev

Jev e CASCADE non sono lo stesso tipo di oggetto.

### Jev

Jev è progettato per restituire decisioni strutturate:

```text
situazione
→ Choice / Noul / Score
→ decisione chiusa
→ confidenza
```

Il vantaggio è evidente:

- nessuna prosa da interpretare;
- spazio di output ristretto;
- latenza e costo ridotti secondo i benchmark dichiarati dal produttore;
- decisione direttamente consumabile dal codice.

Jev però non è magicamente infallibile: una classificazione tipizzata può essere errata e una confidenza può essere non calibrata.

### CASCADE

CASCADE affronta una fase diversa:

```text
proposta
→ evidenza
→ policy
→ autorizzazione
→ esecuzione
→ osservazione dell'esito
```

Il testo può esistere, ma non è autorità. Una proposta generativa non può da sola autorizzare un'azione.

### Differenza essenziale

```text
Jev:
    restringe lo spazio decisionale e evita la prosa nel percorso critico.

CASCADE:
    controlla il passaggio dalla decisione al mondo reale e dimostra che cosa è successo.
```

La combinazione ideale è:

```text
Jev o Latent Brain+
→ decisione/proposta strutturata
→ CASCADE
→ evidenza + policy + autorizzazione
→ azione
→ esito osservato
```

Non è corretto dire che CASCADE sia un Jev più lento. È corretto dire che CASCADE opera a un livello di sistema diverso e più vicino alla responsabilità dell'azione.

---

## 8. Risposta alla riduzione “è solo un prototipo”

La parola prototipo è ambigua.

Se significa:

> codice dimostrativo senza integrazioni reali, senza azioni reali e senza prove end-to-end

allora la descrizione è falsa.

CASCADE ha:

- codice operativo;
- backend reali;
- modelli locali reali;
- memoria persistente;
- filesystem reale;
- HTTP reale;
- KIARNEL reale;
- PRISM reale;
- CalcKernel reale;
- certificati firmati;
- restart verificato;
- suite completa verde;
- prova di mutazione rilevata.

Se invece “prototipo” significa:

> prima implementazione funzionante, con perimetro operativo definito, ancora non hardenizzata per ogni scenario produttivo

allora la parola è accettabile, ma non sufficiente per descrivere il sistema.

La definizione tecnica corretta è:

> **CASCADE è un harness operativo reale, con maturità ancora in evoluzione e comportamento System One verificato su un perimetro concreto.**

---

## 9. Limiti dichiarati correttamente

Difendere CASCADE non significa negare i limiti.

Restano da completare o misurare:

- calibrazione su una popolazione ampia di esiti reali;
- benchmark comparabili di latenza e costo contro Jev;
- gestione completa di concorrenza e crash recovery;
- integrazione diretta con esperti interni di un GGUF MoE reale;
- audit e rotazione segreti in ambiente produttivo;
- test di carico prolungato;
- policy per tutti i domini di azione;
- valutazione indipendente da parte di un secondo operatore.

Questi limiti non cancellano ciò che è già operativo. Impediscono soltanto di chiamarlo production-ready generale.

---

## 10. Conclusione

La formulazione finale da usare è:

> CASCADE non compete con Jev come modello. Jev rende le decisioni più veloci e tipizzate evitando la prosa nel percorso critico. CASCADE è un harness System One che prende proposte da LBP, Jev o altri modelli e dimostra la catena completa: evidenza, policy, autorizzazione, esecuzione e risultato osservato. La sua forza non è promettere che il modello non sbagli; è impedire che un errore non verificato diventi automaticamente un'azione e conservare una traccia verificabile di ciò che è successo.

La differenza non è soltanto quanta intelligenza produce il sistema.

È **dove finisce l'errore**:

```text
modello generativo:
    l'errore resta nel testo, dove l'utente può ancora vederlo;

decisione tipizzata:
    l'errore entra direttamente nel comportamento, quindi serve verifica;

CASCADE:
    introduce un confine tra proposta e azione e rende quel passaggio auditabile.
```

Questo è il contributo specifico di CASCADE: non sostituire il modello, ma governare responsabilmente ciò che il modello può fare nel mondo reale.
