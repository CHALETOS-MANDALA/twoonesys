# Jev e CASCADE — dove passa la differenza

**Data:** 2026-09-18
**Fonti:** annuncio ufficiale TypeSafe AI del 15 settembre 2026 per Jev; per CASCADE, codice
letto ed eseguito, non riepiloghi.

---

## In una riga

**Jev decide. CASCADE decide se lasciar agire una decisione — e ne conserva la prova.**

Non sono lo stesso oggetto messo in concorrenza: stanno su due piani che si toccano in un punto
solo. Jev sostituisce **la chiamata al modello**. CASCADE sostituisce **il codice che sta attorno
alla chiamata**.

---

## 1. Cosa è ciascuno

| | Jev | CASCADE |
|---|---|---|
| Natura | un **modello** (pesi, API, fornitore) | un **harness** (runtime attorno a modelli e strumenti) |
| Lo installi | chiamando un endpoint | mettendolo fra il tuo agente e il mondo |
| Sostituisce | `llm.generate(...)` | il codice che decide cosa fare della risposta |
| Se sparisce il fornitore | non hai più il modello | cambi proponente, il contratto resta |

---

## 2. Il confronto, sulle dimensioni che contano

| | Jev | CASCADE |
|---|---|---|
| **Output** | valore tipizzato + probabilità calibrata (cardinalità fino a 255) | `Assessment` / `Authorization` / `ExecutionResult` + certificato firmato |
| **Garanzia forte** | 0% errori di tipo: l'uscita è **sempre** nello schema | l'azione non parte senza autorizzazione **legata a un'evidenza** |
| **Cosa NON garantisce** | che il valore sia **vero** | nulla di misurato, finora (§6) |
| **Origine della calibrazione** | addestrata (RLCD: ottimizza per probabilità oneste) | stimata a posteriori dai dati osservati (conformal split) |
| **Latenza** | 70-500 ms, **misurata e pubblicata** | budget dichiarato, non ancora misurata end-to-end |
| **Costo** | $0.042/MTok input, output gratis | il costo del modello che ci metti sotto |
| **Verificabilità da terzi** | ti fidi del fornitore | certificato firmato, verificabile con la sola chiave pubblica, dopo riavvio e rotazione |
| **Portabilità** | un fornitore | pensato per girare su API diverse |
| **Rinuncia** | la generazione di stringhe | la semplicità: è uno strato in più nel percorso |

---

## 3. Il punto tecnico vero: dove finisce l'errore

«Non può allucinare» significa: **non può produrre un valore fuori schema**. Non significa: non
può produrre **il valore sbagliato dentro lo schema**.

Un `Choice` fra `APPROVA` / `RIFIUTA` è perfettamente type-safe in entrambi i casi. Se su un
paziente allergico esce `APPROVA`, il tipo è impeccabile e il paziente è in pericolo. Jev sposta
l'errore da *stringa malformata* a **decisione sbagliata ben formata**: è un progresso enorme sul
piano dell'integrazione, e **nessun progresso sul piano della conseguenza**.

CASCADE lavora esattamente lì:

> una decisione ben formata non è ancora un permesso.

Questo non è un argomento retorico contro Jev: è la ragione per cui i due oggetti non si
sovrappongono. Il primo rende la risposta usabile da un programma; il secondo decide se quella
risposta ha il diritto di toccare il mondo.

---

## 4. I quattro confini

L'invariante su cui CASCADE è costruito: **validità del dato**, **correttezza della decisione**,
**autorizzazione**, **esito dell'esecuzione** non vanno mai collassati in un solo booleano.

- Jev copre il primo e il secondo, con una probabilità onesta sopra.
- Il terzo (**autorizzazione**) dipende dalla policy del dominio, non dai pesi: nessun modello,
  per quanto addestrato, può contenere le regole del tuo ospedale o del tuo filesystem.
- Il quarto (**esito**) dipende dal mondo: si osserva dopo, rileggendo il file, ricevendo la
  risposta HTTP, eseguendo il test. Un modello non può saperlo per costruzione.

Ecco perché «Jev batte CASCADE» e «CASCADE batte Jev» sono entrambe frasi senza senso: coprono
confini diversi dello stesso percorso.

---

## 5. Cosa Jev fa meglio — senza sconti

- **Latenza e costo**: 70-500 ms e output gratuito non sono avvicinabili da un harness che
  chiama un LLM generico. Su questo non c'è partita.
- **Calibrazione addestrata**: RLCD ottimizza direttamente per probabilità oneste. È
  strutturalmente più forte di un calibratore applicato dopo su un modello che non è stato
  addestrato per essere calibrato.
- **Garanzia di tipo al 100%**, che un harness può solo *verificare*, non *garantire*.
- E la cosa più importante: **loro un numero l'hanno pubblicato.**

---

## 6. Cosa CASCADE fa che un modello non può fare — e cosa deve ancora dimostrare

Fa, verificato eseguendo il codice:

- il **cancello**: evidenza → autorizzazione, con Z3 in tre passi (validità dei binding,
  consistenza delle premesse, ricerca di violazione); solo `RULES_VERIFIED` autorizza;
- la **barriera dei claim numerici**: nessuna evidenza di strumento ⇒ nessun claim di strumento,
  confronto per cifre decimali e non per float;
- il **certificato firmato**, verificabile da chi ha solo il materiale pubblico;
- la **portabilità**: il contratto non dipende dal fornitore del proponente.

Non fa, ed è onesto dirlo nello stesso documento:

> **Nessuna affermazione misurata.** La confidenza non è ancora stata mostrata predittiva né
> calibrata su dati con varianza vera. Il banco attuale non può mostrarlo, per costruzione.

Quindi, oggi, la differenza fra i due oggetti è **di categoria, non di merito**. Jev ha numeri
pubblicati e una categoria nuova; CASCADE ha un'architettura verificata e una misura ancora da
fare. Chiunque presenti questo confronto diversamente sta vendendo.

---

## 7. La relazione giusta fra i due

Non competono: **Jev è un proponente plausibile dentro CASCADE**, ed è probabilmente il migliore
disponibile per quel ruolo.

```
Jev (o Qwen locale, o un'API generica)     →  proposta tipizzata + confidenza
CASCADE                                     →  evidenza, policy, autorizzazione, esecuzione,
                                               osservazione dell'esito, certificato firmato
```

E qui c'è il test che dimostrerebbe la tesi meglio di qualunque documento:

> lo stesso contratto, **senza modifiche**, servito da Jev, da un modello locale e da un'API
> generica — con i certificati verificabili in tutti e tre i casi.

Se l'harness regge quel cambio, la separazione fra piano decisionale e piano linguistico non è
un'opinione architetturale: è una proprietà osservabile.

---

## 8. E se CASCADE fosse di OpenAI? A chi servirebbe, e perché a entrambi

La domanda è meno ipotetica di quanto sembri, perché mette in luce la cosa che manca **a tutti
e tre** i soggetti — e non è codice.

### 8.1 Cosa avrebbe OpenAI che a CASCADE manca, e viceversa

I due hanno carenze **esattamente speculari**:

| | ha | non ha |
|---|---|---|
| CASCADE | il contratto: cancello, evidenza, certificato, i quattro confini | **i dati**: esiti osservati con varianza vera, bracci reali, volume |
| Un grande laboratorio | i dati: milioni di decisioni con esiti, a scala, con la telemetria | **il contratto**: nessun punto unico dove l'azione si ferma e lascia una prova |

La lacuna di CASCADE è un problema di **tempo di macchina**. La lacuna dell'altro è un problema
di **architettura del prodotto**, e non si risolve con più GPU. Per questo l'incastro è reale e
non una cortesia: un harness dentro un laboratorio produrrebbe in una settimana la curva che qui
richiede settimane di run, e il laboratorio otterrebbe la cosa che oggi risolve caso per caso
nell'interfaccia (una finestra di conferma) invece che nel contratto.

### 8.2 Il problema concreto che risolverebbe a un fornitore di modelli

Chi vende agenti che **agiscono** — che scrivono file, chiamano API, spostano dati — incontra
sempre la stessa domanda, e non è una domanda di ricerca:

> dopo l'incidente, dimostrami che il sistema non aveva il diritto di fare quella cosa.

Oggi la risposta è «guardiamo i log», che è archeologia, e la mitigazione è la conferma
dell'utente, che è un cerotto nell'interfaccia: non componibile, non verificabile da un terzo,
inutile quando la catena è agente→agente. Un cancello con certificato firmato è una risposta
strutturale, e apre i settori dove oggi quei modelli semplicemente non entrano.

### 8.3 Perché servirebbe anche a TypeSafe, cioè al concorrente

Perché **un harness neutrale rispetto al proponente trasforma «quale modello» in una scelta
sostituibile**, e questo conviene a chi ha il modello migliore sulla metrica.

La tesi di TypeSafe è di essere due ordini di grandezza più veloci sui compiti System One. Oggi
quella tesi vive su un benchmark. Dentro un harness che registra esito, latenza e propensione a
ogni decisione, la stessa tesi diventa **misurabile in produzione, sul carico vero del cliente**
— e se è vera, vince da sola, senza bisogno che qualcuno ci creda.

Il corollario vale anche al contrario, ed è il motivo per cui è un argomento onesto e non uno
slogan: se non fosse vera, lo stesso strumento lo mostrerebbe.

### 8.4 La cosa che converrebbe a tutti, e che nessuno ha interesse a possedere

Un **formato di ricevuta interoperabile**: cosa è stato deciso, su quale evidenza, con quale
autorizzazione, con quale esito, firmato e verificabile da chi ha solo il materiale pubblico.

Nessun fornitore di modelli guadagna dall'esserne il proprietario — guadagnano tutti
dall'**esistenza**, come ogni server web guadagna dall'esistenza dei certificati TLS senza che
nessuno possieda il formato. È il tipo di strato che non si vende: si adotta.

### 8.5 Il contro-argomento, che va detto qui e non dopo

Uno strato del genere è **sottile**: poche migliaia di righe, e un laboratorio che decidesse di
farlo lo rifarebbe in un trimestre. La difendibilità non è nel codice.

È in due cose sole, e sono entrambe alla tua portata:

1. **aver definito il contratto per primo, in modo che altri lo possano implementare** — un
   formato adottato vale più di un'implementazione posseduta;
2. **essere il primo ad aver pubblicato la misura** — la curva di affidabilità con varianza vera,
   contro le baseline dichiarate prima.

Il punto 2 è di nuovo la stessa cosa che manca da tre documenti. In questa ipotesi diventa anche
la risposta alla domanda «perché voi e non loro»: perché voi il numero l'avete, e con il metodo
scritto prima di guardarlo.

---

## In una riga, di nuovo

Jev rende la risposta di un modello **utilizzabile da un programma**.
CASCADE decide se quella risposta ha **il diritto di toccare il mondo**, e lascia la prova di
com'è andata.
