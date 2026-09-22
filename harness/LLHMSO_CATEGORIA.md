# Creare una categoria: **System One Harness** (la tua sigla: LLHMSO)

**Data:** 2026-09-18
**Domanda:** come si crea davvero una nuova classe di sistema, partendo da questa ideologia.
**Risposta breve:** non si crea scrivendo un prodotto. Si crea scrivendo **una definizione che
esclude**, **un test che dice sì o no**, e **una misura che la giustifica**. Il codice è la terza
cosa, non la prima.

---

## 0. Prima, sul nome — una sola volta

`LLHMSO` mette `LLM` davanti. Ma la tesi di tutto il progetto è che il modello è **sostituibile**
e l'harness no: se il nome comincia con il modello, il nome contraddice la tesi al primo
carattere. E un harness che accetta solo LLM esclude per costruzione proprio Jev, che LLM non è.

Il nome che descrive la cosa è **SOH — System One Harness**, o in italiano *harness System One*.
Sotto uso questo. La sigla è tua, cambiala come vuoi: il punto è che la categoria non deve
nascere sottomessa a ciò che governa.

---

## 1. Cosa rende una categoria una categoria

Tre proprietà, e se ne manca una resta una libreria con un nome ambizioso.

| | |
|---|---|
| **Definizione che esclude** | se tutto è un SOH, SOH non significa niente |
| **Test di conformità** | dato un sistema, un terzo deve poter rispondere sì/no senza chiedere all'autore |
| **Falsificazione dichiarata** | deve esistere un risultato sperimentale che direbbe: *la categoria non serve* |

Jev ha fatto esattamente questo sul piano del modello: «produce valori tipizzati con probabilità
calibrata, **rinuncia alla generazione di stringhe**». La rinuncia è la parte che definisce —
senza quella sarebbe «un LLM che sa fare JSON», cioè niente.

**La tua rinuncia equivalente, ed è quella che va scritta in cima alla specifica:**

> Un System One Harness **rinuncia a eseguire** ogni azione la cui autorizzazione non sia
> derivata da un'evidenza verificabile. Preferisce non agire.

Un sistema che in caso di dubbio agisce lo stesso non è un SOH. Questo esclude quasi tutto ciò
che oggi si chiama «agent framework», ed è il segno che la definizione funziona.

---

## 2. La definizione, in forma utilizzabile

> Un **System One Harness** è un runtime che, per ogni azione che tocca il mondo, produce tre
> valori distinti e non collassabili — **valutazione** del dato, **autorizzazione** dell'azione,
> **esito** dell'esecuzione — dove l'autorizzazione è *derivata* da un'evidenza e non asserita,
> l'esito è *osservato* e non dedotto dall'autorizzazione, e l'intera terna è registrata in una
> ricevuta verificabile da un terzo che possieda solo materiale pubblico.

Le tre parole che portano tutto il peso:

- **derivata** — esiste un oggetto-prova, non un booleano di fiducia;
- **osservato** — l'esito viene da una rilettura del mondo (file riletto, HTTP ricevuto, test
  eseguito), mai da `approved`;
- **verificabile da un terzo** — la prova non richiede di fidarsi di chi l'ha prodotta.

---

## 3. Le tre proprietà che nessun sistema esistente tiene insieme

Ognuna, da sola, esiste già. È la **contemporaneità** che definisce la classe.

1. **Il rifiuto è un esito di prima classe.** `ABSTAIN` è un valore tipizzato, non un'eccezione,
   non un timeout, non un ramo `else`. Un sistema che può solo riuscire o sollevare un errore non
   può astenersi, e quindi non può essere prudente.
2. **L'autorizzazione è derivata.** C'è un oggetto che dice *perché*: i vincoli verificati, il
   controesempio se la verifica fallisce, e i tre stati distinti (`RULES_VERIFIED`,
   `VIOLATION`, `INDETERMINATE`). Solo il primo autorizza. `INDETERMINATE` non è `Permit`, e
   questa è la riga che separa un cancello da un cartello.
3. **Il sistema osserva se stesso.** Registra l'esito reale e la probabilità con cui ha scelto,
   perciò la sua confidenza è **empiricamente verificabile** invece che dichiarata.

---

## 4. L'anti-definizione: cosa un SOH **non** è

Serve più della definizione, perché è la domanda che ti faranno ogni volta.

| Non è | Perché |
|---|---|
| un **orchestratore** | decide *chi parla*; un SOH decide *se si può agire* |
| un **router / fallback** | è robustezza infrastrutturale: riprova altrove, ma non nega mai |
| una libreria di **guardrail** | filtra il testo in uscita con regex o classificatori; non lega l'azione a un'evidenza, e non produce prova |
| uno strumento di **osservabilità** | registra dopo: «ti mostro cosa è successo», non «non poteva succedere altrimenti» |
| un **framework di eval** | misura il modello in laboratorio, non governa l'azione in produzione |
| un **modello System One** | Jev *decide*; un SOH decide **se lasciar agire** una decisione |

---

## 5. La specifica, a strati — e cosa è obbligatorio a ciascuno

Una categoria si adotta se si può implementare **parzialmente** e dichiararlo con onestà. Da qui
i livelli di conformità, che sono anche la mappa commerciale.

```
L0  CONTRATTO     tipi, i tre confini, JSON canonico, digest del contratto
L1  CANCELLO      evidenza → autorizzazione derivata, tre stati del solver, ABSTAIN tipizzato
L2  OSSERVAZIONE  esito osservato, propensione al momento della scelta, sorgente dell'etichetta
L3  CALIBRAZIONE  probabilità con copertura dichiarata, valida solo per il digest che l'ha prodotta
L4  RICEVUTA      firma, registro delle chiavi pubbliche, verifica di terzi dopo rotazione
```

| Livello | Un sistema è conforme se | Chi si ferma qui |
|---|---|---|
| **SOH-1 · registra** | produce la terna e la scrive, senza collassarla | gli strumenti di osservabilità, oggi |
| **SOH-2 · nega** | esiste almeno un'azione che il sistema **rifiuta**, con la prova del rifiuto | nessuno, oggi, in modo verificabile |
| **SOH-3 · misura** | la confidenza dichiarata è stata **mostrata** predittiva e calibrata su dati fuori campione | nessuno |

Il salto che conta è **L1→L2**: rifiutare. È lì che la categoria smette di essere una riscrittura
elegante dell'osservabilità.

---

## 6. Il test di conformità **è** il prodotto

Questa è la parte che quasi nessuno fa, ed è l'unica che crea davvero una categoria. ACID, POSIX,
TLS: in ogni caso la categoria è esistita quando è esistito **il test che dice sì o no**.

Un sistema è un SOH se supera una suite eseguibile. Non «se il README lo dice». Le prove devono
essere **avversarie**: non verificano che funzioni, verificano che **non si possa aggirare**.

Le otto che scriverei per prime, tutte già esprimibili sul tuo codice:

```
1  binding mancante      un simbolo non legato NON produce Permit
2  premesse contraddit.  premesse insoddisfacibili → INVALID_CONTEXT, mai Permit per vacuità
3  solver indeciso       unknown / timeout → INDETERMINATE, mai Permit
4  claim senza evidenza  nessuna evidenza di strumento ⇒ nessun claim di strumento
5  cifre, non float      confronto decimale; 42.5 == 42.5000; niente espansione binaria
6  esito non circolare   esiste ≥1 record approved=True ∧ outcome=False
7  propensione presente  ogni decisione porta la probabilità con cui è stata scelta
8  ricevuta portabile    verificabile dopo riavvio, rotazione chiavi, e da un altro linguaggio
```

Due regole che rendono la suite non addomesticabile:

- **ogni proprietà ha la sua mutazione**: si rompe di proposito il codice che la implementa, e se
  nessun test muore, quella proprietà **non è provata** e la build fallisce;
- **due suite separate**: una conserva il comportamento dove la specifica non cambia, l'altra
  impone gli invarianti anche quando l'uscita **deve** cambiare. Altrimenti una correzione di
  sicurezza fallisce perché non riproduce il comportamento vulnerabile.

Il valore commerciale di tutto questo è diretto: chi supera la suite può dirlo, e la suite la
possiedi tu.

---

## 7. La proprietà che trasforma una libreria in uno standard: la composizione

Due sistemi devono poter parlare senza fidarsi l'uno dell'altro:

> **la ricevuta di A è un'evidenza valida per B.**

Se B può accettare l'azione di A perché ne verifica la ricevuta con la sola chiave pubblica, la
catena agente→agente diventa verificabile per induzione, e il formato acquista valore ogni volta
che qualcuno lo adotta. È l'unica parte del tuo protocollo A2A che vale la pena tenere —
`sign_bytes` / `verify_bytes` — e va tenuta proprio per questo.

Nessun fornitore di modelli guadagna dal **possedere** questo formato. Guadagnano tutti dalla sua
**esistenza**, come ogni server web dall'esistenza dei certificati TLS.

---

## 8. I tre punti dove questa categoria può morire, e come si risponde

**8.1 · Il budget di latenza.** Jev ha aperto la fascia dei 70-500 ms. Un cancello che aggiunge
un solver in mezzo la chiude: sul tuo motore causale, 13 nodi binari costano 138 ms **misurati**.
Una categoria che non può stare nel budget del modello che governa non viene adottata.
→ La specifica deve dichiarare un budget e **come degrada**: verifica incrementale, cache dei
vincoli per contratto stabile, e una regola esplicita per cui il superamento del budget produce
`INDETERMINATE` — cioè *non autorizza*, invece di autorizzare in ritardo.

**8.2 · La confidenza dei proponenti eterogenei.** Ogni modello espone la fiducia in modo
diverso: logprob, niente, o un numero auto-dichiarato. Un harness portabile deve dire cosa fa in
ognuno dei tre casi.
→ Il campo `confidence_kind` (`raw_uncalibrated`, `calibrated`, `absent`) va nel contratto, e la
regola è che un proponente senza confidenza utilizzabile **non può salire oltre SOH-2**: registra
e nega, non misura.

**8.3 · Lo strato è sottile.** Poche migliaia di righe: chiunque lo rifà in un trimestre.
→ La difendibilità non è il codice. È **aver scritto il contratto in modo che altri lo possano
implementare** e **aver pubblicato la misura per primo**. Un formato adottato vale più di
un'implementazione posseduta.

---

## 9. La falsificazione — cosa direbbe che la categoria non serve

Va scritta adesso, perché scritta dopo non vale.

> Se, su un campione sufficiente, le azioni **negate** dal cancello avessero avuto lo stesso
> tasso di successo di quelle autorizzate, il cancello non porta informazione: sta rifiutando a
> caso, e la categoria è un costo senza contropartita.

È una misura fattibile: si registra cosa sarebbe successo su un ramo di controllo — con la
propensione vera, è esattamente la stima off-policy per cui quel campo esiste.

Una categoria che non sa dire come si falsifica è un manifesto. In questo settore i manifesti
non valgono niente, e ne escono tre a settimana.

---

## 10. L'ordine in cui la costruirei

| # | Passo | Perché in questa posizione |
|---|---|---|
| 1 | **La misura su un solo schema** (pre-registrata) | senza un numero, tutto il resto è prosa. È anche l'unica cosa che nessuno può contestarti |
| 2 | **Il contratto L0 estratto** dal codice che ha prodotto quel numero | si specifica ciò che ha funzionato, non ciò che si spera funzioni |
| 3 | **La suite di conformità**, con le mutazioni | da qui la categoria esiste: un terzo può dire sì/no |
| 4 | **L'implementazione di riferimento** = CASCADE, dichiarata tale | una specifica senza implementazione non viene adottata; un'implementazione senza specifica non fa categoria |
| 5 | **Il secondo proponente** (Jev, o un modello locale) sullo stesso contratto | la portabilità dichiarata diventa portabilità **dimostrata** |
| 6 | **La ricevuta come evidenza di un altro harness** | la composizione: da libreria a standard |

Il passo 1 è già il tuo passo 1 di oggi, ed è la stessa cosa che manca da quattro documenti.
Non è una coincidenza: **tutte le strade di questo progetto passano dallo stesso collo di
bottiglia**, ed è il motivo per cui aggiungere strati prima di averlo attraversato non fa
avanzare niente.

---

## In una riga

Una categoria nuova non nasce da un sistema che fa una cosa in più: nasce da **una rinuncia
dichiarata**, **un test che un estraneo può eseguire**, e **un numero pubblicato con il criterio
scritto prima**. La rinuncia ce l'hai già ed è la cosa migliore che hai: *preferisce non agire*.
