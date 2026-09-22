# CASCADE — quanto manca, quali bug, e la strada verso un SaaS

**Data:** 2026-09-18 · ultima analisi della sessione
**Base:** log reali letti dal disco, non riepiloghi.

---

## A. Quanto manca

### A.1 Il dato nuovo, e non è buono

Il run si è fermato a 72 record. Letto ora:

```
esiti:            60 True,  12 False
posizioni dei fallimenti:  [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71]
```

**Zero fallimenti nei primi 60, dodici consecutivi dopo.** Non è un tasso di fallimento: è
una rottura totale dalla posizione 60 in poi, e non si è più ripresa.

E il segnale positivo di ieri si è indebolito appena sono arrivati altri dati:

```
ieri  (4 fallimenti sani):  AUC = 0.852   IC95 = [0.695, 0.970]   esclude 0.5
oggi  (5 fallimenti sani):  AUC = 0.702   IC95 = [0.390, 0.939]   CONTIENE 0.5
```

**Quindi oggi non si può concludere niente, né in positivo né in negativo.** Un campione in
più ha spostato l'intervallo fino a coprire il caso. È esattamente ciò che significa «con 4-5
esempi della classe rara non hai una misura»: avevo ragione a chiamarlo preliminare, e sarebbe
stato facile raccontarlo come una vittoria.

### A.2 La definizione di «finito», per non spostarla dopo

> Su uno schema decisionale dichiarato, con **≥ 25-30 esiti della classe minoritaria**,
> propensione registrata al momento della scelta, **ground truth indipendente
> dall'approvazione**, valutazione su dati **fuori campione**, e pubblicazione congiunta di
> **calibrazione** (ECE, curva) **e discriminazione** (AUC con intervallo), contro le tre
> baseline dichiarate prima di guardare i risultati.

### A.3 La distanza, in numeri

| | oggi | serve |
|---|---|---|
| esiti utilizzabili | 64 (di cui 5 della classe rara) | ≥ 25-30 della classe rara |
| decisioni totali al tasso attuale | 72 | **~250-300** |
| campi del log | propensione ✓, label_source ✓, digest ✓ | + **identità del braccio** |
| ground truth | `approved == outcome` in 72/72 | **indipendente**, da verificare |
| stabilità del banco | si rompe dopo ~60 run | reggere 300 run |

**Stima onesta: 2-4 settimane part-time**, e la parte lunga non è scrivere codice — è far
girare il banco di prova abbastanza a lungo senza che si rompa, con un compito abbastanza
vario da fallire davvero qualche volta.

Il codice che manca è poco. Quello che manca è **tempo di macchina e varianza vera.**

---

## B. I bug, in ordine di quanto bloccano

### B1 — La rottura al record 60 🔴 *blocca tutto*
Dodici fallimenti consecutivi dopo 60 successi puliti, e da lì confidenza che si inchioda a
`1.0` esatto. Finché non sai cosa cade, ogni run lungo produce dati avvelenati.
**Come si trova:** logga l'eccezione dell'esecutore per ogni record, non solo l'esito. Ora
`outcome=False` non dice *perché*.
*Effort: mezza giornata di diagnosi.*

### B2 — `approved == outcome` in 72/72 🔴 *invalida la misura*
Zero casi di azione approvata che poi fallisce, in 60 esecuzioni. Se l'esito è **derivato**
dall'approvazione invece di essere osservato dopo, stai calibrando la confidenza del sistema
contro la sua stessa decisione: il numero finale non significherebbe niente, per quanto bello.
**Come si verifica:** leggi il codice che scrive `outcome`. Se viene dalla stessa espressione
che decide `approved`, è circolare e va separato (l'esito deve venire da una lettura del mondo:
file riletto, HTTP ricevuto, test eseguito).
*Effort: un'ora per verificare, mezza giornata per separarlo.*

### B3 — `action` costante 🟠 *rende inutile la propensione*
`verified_model_action` in tutti e 72 i record. La propensione è registrata bene e coerente
(0.25 osservata 18/72, 0.75 osservata 54/72), ma senza sapere **quale braccio** è stato scelto
non puoi stimare nessuna politica alternativa: IPS e doubly-robust restano inservibili, e quel
campo è contabilità senza scopo.
*Effort: un campo in più nel record.*

### B4 — `negotiate()` 🟡
`best = max(pool, key=reputation/price if price>0 else inf)`: un agente **gratuito vince
sempre**, anche con reputazione zero. E `estimated_quality` viene calcolata, usata come filtro,
e poi ignorata nel ranking — mentre il commento sopra dichiara il contrario.
*Effort: dieci righe.*

### B5 — `proof_constraints` 🟡
Contiene stringhe formattate (`"P(incidente)=0.317"`), non i vincoli Z3. È una nota leggibile
dentro un campo che si chiama «prova».
*Effort: un'ora.*

### B6 — Replay buffer FIFO 🟢 *fuori dalla v1*
`SelectiveReplayBuffer` non è selettivo (punteggi costanti a 1.0, eviction sull'indice 0) e
`train_task` aggiunge `x[0], y[0]` — il primo campione del batch, esattamente ciò che il README
dichiara di aver corretto. Riguarda L2, che è fuori dalla v1: lascia stare, ma togli la frase
dal README.

### B7 — `cascade/` non è un repository git 🔴 *blocca la vendita, non il codice*
Niente storia, niente licenza, niente che dica a un compratore o a un datore di lavoro **cosa
esattamente sta guardando**. È mezz'ora di lavoro e vale più di una settimana di feature.

**Totale: 3 bug che bloccano (B1, B2, B7), 2 che sporcano (B3, B4), 2 cosmetici.**
Non è un progetto pieno di bug. È un progetto a cui manca **una misura**.

---

## C. Come diventa un SaaS vendibile

### C.1 Cosa vendi davvero

Non «un harness». Questo:

> **La prova, dopo un incidente, che un'azione automatica non poteva avvenire senza
> un'autorizzazione legata a un'evidenza — e la traccia firmata di cosa è successo davvero.**

Chi compra agenti che *agiscono* (scrivono file, chiamano API, muovono dati) ha un problema che
nessuna dashboard risolve: quando qualcosa va storto, deve dimostrare cosa il sistema aveva il
diritto di fare. Oggi la risposta è «guardiamo i log», che è archeologia.

### C.2 Perché non sei in competizione con gli osservabilisti

Langfuse, Arize, LangSmith e simili fanno **osservabilità**: registrano tutto e te lo mostrano.
Tu fai una cosa diversa e più difendibile: **un cancello**. L'azione non parte senza un grant
legato all'evidenza, e il certificato è firmato e verificabile dopo un riavvio e dopo una
rotazione di chiavi.

«Ti mostro cosa è successo» è un prodotto affollato. «Posso dimostrare che non poteva succedere
altrimenti» no.

### C.3 La forma giusta per **una persona sola**

| Scelta | Perché per te |
|---|---|
| **Self-hosted, non cloud multi-tenant** | zero infrastruttura da gestire, zero reperibilità notturna, zero bolletta. E i compratori regolamentati preferiscono che i dati non escano |
| **SDK prima, dashboard dopo** | il tuo valore è nel contratto, non nei grafici. Un dashboard richiede design e manutenzione che non hai tempo di fare |
| **Open-core** | distribuzione senza rete commerciale: il nucleo aperto ti porta gli utenti, il resto si paga |
| **Un solo dominio d'azione all'inizio** | scrittura su filesystem, o chiamate HTTP. Non tutti e due |

**Cosa è aperto:** SDK, contratti, barriera, guard, log firmato.
**Cosa si paga:** il verificatore dei certificati, i pacchetti di policy, la conservazione a
lungo termine, e **l'export per l'audit** — cioè il documento che qualcuno deve consegnare.

### C.4 Il minimo vendibile

```python
from cascade import guarded

@guarded(policy="fs.write.sandbox")
def scrivi_report(path, contenuto):
    ...
# blocca, oppure esegue e restituisce una ricevuta firmata
```

Più: un comando che verifica una ricevuta (`cascade verify receipt.json` → chi, cosa, quando,
con quale evidenza, con quale chiave), e un repo di esempio dove un agente viene **bloccato**
e la ricevuta lo dimostra.

Quella demo — un agente fermato, con la prova — è il tuo materiale di vendita. Non le slide.

### C.5 I primi tre passi, in ordine

1. **Pubblica il calibratore conformal da solo.** ~120 righe, numpy, risolve un problema che ha
   chiunque usi API senza logprob. Non ti dà soldi: ti dà la credenziale con cui ti prendono sul
   serio. *1 settimana.*
2. **Chiudi B1, B2, B7 e produci la curva.** Senza quella, «calibrato» è una parola.
   *2-4 settimane part-time.*
3. **Tre design partner, non tre clienti.** Cerca chi ha agenti che toccano la produzione. Chiedi
   trenta minuti. **Non vendere**: chiedi cosa dovrebbero consegnare se domani un agente
   combinasse un guaio. Se tre persone descrivono lo stesso documento, quello è il prodotto.

### C.6 I numeri, come ordini di grandezza (non sono un consulente finanziario)

- Strumenti per sviluppatori self-hosted in area compliance: indicativamente **€500-2.000/mese
  per team** nella fascia piccola; sopra serve un commerciale, e tu non ce l'hai.
- **Primo cliente pagante realistico: 6-12 mesi**, da solo e part-time.
- La strada che paga **prima** resta la consulenza sulla stessa competenza: **400-900 €/giorno**
  in Europa, senza vendere niente.

### C.7 Il vento normativo, con la data giusta

L'AI Act europeo obbliga a tracciabilità e sorveglianza umana per i sistemi ad alto rischio, ma
il Digital Omnibus ha spostato le scadenze: **Annex III al 2 dicembre 2027**, **Annex I al
2 agosto 2028**. Restano applicabili da agosto 2026 i soli obblighi di trasparenza dell'Art. 50.

Tradotto: **hai runway, non urgenza.** Nel 2026 nessuno compra per paura della multa. Nel 2027
sì — e a quel punto conterà chi ha già un prodotto in uso, non chi ha una buona idea.

### C.8 I tre modi in cui questo fallisce

1. **Aggiungi funzioni invece di misurare.** Il progetto 95.
2. **Costruisci il cloud multi-tenant.** Ti mangia tutto il tempo e ti mette in concorrenza
   frontale con aziende finanziate.
3. **Vendi la promessa prima della prova.** È l'unica cosa che ti distingue: se la bruci
   raccontando un numero non misurato, resta un harness come tanti.

---

## In una riga

Non ti manca codice: ti mancano **tre bug bloccanti e una misura**. Il codice è a posto quanto
serve. Il passo che vale più di tutti gli altri messi insieme è far girare il banco di prova
fino a quando la classe rara ha abbastanza esempi — e poi pubblicare il numero, qualunque esso
sia.

---

## Risoluzione B1/B2/B3 — sessione successiva (2026-09-18)

**Metodo:** log riletti dal disco con Python + una proposta LBP reale eseguita (non lette).

### B1 — la rottura al record 60 **non è un crash**

Due fatti misurati:

1. I timestamp dei 72 record hanno **cadenza costante ~62 s** su tutta la serie, nessun buco:
   il processo non è caduto. I file di azione esistono **solo per 000-059**; i record 060-071
   hanno `approved=False`. I 12 fallimenti sono il **clamp contiguo del banco**
   (`allow / state = index < valid`, con `valid=60`), non un guasto del servizio.
2. La "confidenza inchiodata a 1.0" è la **coerenza SIFT saturata**: `confidence_kind` è
   `coherence_uncalibrated`. Misurato ora: su un prompt banale la coerenza è `1.0000`; su tre
   prompt difficili è `0.88 / 0.93 / 0.90`. La varianza **c'è**, ma i prompt del banco
   (`... numero {index}`) sono troppo banali perché il segnale si muova.

→ Fix: clamp **stocastico con seed** (`--fail-rate`, `--seed`) invece del blocco posizionale.
Dimostrato: 120 record, 23 fallimenti sparsi (gap 1-21), nessun blocco.

### B2 — già separati nel codice, il log dei 72 era **stale**

`integrated_workflow.py` scrive `approved=gate_approved` (evidenza) e
`outcome=(action_status=="succeeded")` (esecuzione osservata): due fonti diverse. Il log dei 72
**non ha `action_chosen`** → è precedente a questa separazione. Prova aggiunta:
`test_approved_e_outcome_separati_nel_record`.

### B3 — `action_chosen` esisteva ma il loop non lo scriveva

`SystemOneLoop.settle/process` non avevano il campo, quindi sul percorso System One restava
`None`. Cablato ora, insieme all'`outcome` esplicito dal mondo; i due banchi lo passano.
Prova: `test_action_chosen_viaggia_fino_al_record`.

### Ground truth indipendente

`run_calibration_100.py` ora legge l'`outcome` **dal mondo** (rilettura del file) e produce il
caso `approved=True, outcome=False` (executor che "riesce" senza effetto). Misurato: 6 su 120.

### Suite

`323 passed, 2 skipped` (torch presente). Prima: `321 passed, 2 skipped`.

### Cosa resta (misurato, non supposto)

La curva **reale** richiede un run LBP (~62 s/record → ~4 h per 250) **con prompt sufficientemente
vari da muovere la coerenza**. Con i prompt attuali la curva è degenere qualunque sia la durata.
Il banco ora regge il run; la varianza va aggiunta al set di prompt prima di partire.

