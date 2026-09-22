# Pre-registrazione — Run 2 di calibrazione: TWOONESYS engine come proponente

**Stato: CONGELATA dal commit che introduce questo file.** Da quel momento nessuna
riga si tocca: le modifiche vanno in un documento successivo, datato, che dichiara
cosa è cambiato e perché.

| | |
|---|---|
| Autore | Rubinho (metodo ereditato da PREREGISTRAZIONE_RUN1.md, adattato) |
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine (Rizzo Flow, Spark-X2.5-**1.7B** Q8, :8017) |
| Digest del contratto misurato | `twoonesys-run2-v1` |

---

## 0. Cosa cambia rispetto a RUN1 (dichiarato prima, come la regola impone)

RUN1 era bozza per un proponente generativo (LBP, ~62 s/record, coerenza che
satura a 1.0). RUN2 misura il proponente nuovo: l'engine TWOONESYS, che emette
decisioni tipizzate con probabilità lette dai logit, 0 token generati.

1. **Il claim nasce dall'ancora scelta dall'engine** (argmax sulle probabilità),
   non dalla media pesata: la media è una stima, la barriera vuole la cifra
   dichiarata. (Patch `rizzo_bridge.py` del 2026-09-21, testata.)
2. **L'esito è il verdetto della barriera** (`verdict.ok`): le cifre del claim
   contro l'evidenza del kernel. Non c'è azione su file in questo run: il rischio
   di circolarità approved/outcome di RUN1 §2.3 **non si applica per costruzione**
   (l'esito viene dal kernel, la confidenza dall'engine: due fonti che non si
   toccano). Il controllo sostitutivo è in §2.3 qui sotto.
3. **La verità non è mai hardcoded nel banco**: gli anchor si costruiscono
   attorno al valore che il kernel calcola per l'`n` del record.
4. **Modello piccolo dichiarato**: 1.7B Q8 (scelta del 2026-09-21: test di
   funzionamento prima di liberare disco per il 4B). Se il `model_id` cambia,
   il run si segmenta in due dataset (regola RUN1 §7) e il 4B sarà RUN3.

## 1. L'unica affermazione da misurare

> Sullo schema decisionale di §2, la confidenza emessa dall'engine **predice**
> il successo del claim con AUC ≥ 0.70, **ed è calibrata** con ECE ≤ 0.10
> su 10 bin.

Una sola frase. Le due metà si pubblicano insieme o non si pubblicano.

## 2. Lo schema decisionale e l'oracolo

```
report tecnico (stato) — puo' contenere il valore vero, una stima
        distrattrice, o non contenerlo affatto
        ↓
engine: domanda numeric con 3-4 anchor (ordine mescolato, seed)
        ↓
claim = ancora scelta (argmax), cifre decimali nude — mai float, mai dal kernel
        ↓
run_verified(calc_kind="zeron", n del record, precision=4)
        ↓
outcome = verdict.ok   (le cifre del claim sono un prefisso corretto
                        dell'evidenza calcolata dal kernel QUI)
```

**Vincolo non negoziabile (ereditato):** il valore del claim proviene dalla
risposta del modello. Se provenisse dall'evidenza, l'esito non misura il modello.

### 2.3 Controllo di indipendenza (sostitutivo del controllo di circolarità)

L'esito è funzione del claim e dell'evidenza, mai della confidenza. Verifica
meccanica nel pilota: deve esistere almeno un record con confidenza ≥ 0.8 e
`outcome=False` **oppure** confidenza ≤ 0.5 e `outcome=True`. Se in 20 record
confidenza ed esito si muovono sempre insieme perfettamente, l'oracolo è
sospetto e il run non parte.

## 3. Popolazione e stratificazione

Tre fasce, campionate in proporzione fissa 1/3, `n` che cicla su {1,2,3,4,5}
(zeri di Riemann: il kernel li calcola, il banco non li scrive):

| Fascia | Definizione | Quota | Fallimento atteso |
|---|---|---|---|
| A — facile | stato col valore esplicito; distrattori lontani | 1/3 | ~5% |
| B — media | stato con valore confermato + stima preliminare diversa nell'ultima cifra; i distrattori includono la stima | 1/3 | ~25% |
| C — difficile | stato SENZA il valore per l'`n` chiesto (riporta un altro `n` o dichiara il dato mancante); `allow_abstain=false` forza la scelta | 1/3 | ~50% |

**Verifica preliminare obbligatoria (pilota):** il tasso di successo deve
differire fra le fasce. Se non differisce, la stratificazione va ritarata prima
del run vero e la ritaratura si annota in un documento datato.

Nota onesta: la fascia C misura anche il punto debole documentato dell'engine
(6 confident-wrong su 36 su evidenza mancante, README dell'autore). È il caso
d'uso del cancello: se la confidenza resta alta quando l'evidenza manca, l'AUC
lo vedrà.

## 4. Metriche

**Primarie:** AUC con IC95 (Hanley-McNeil), confidenza → esito. ECE su 10 bin
di uguale ampiezza, con curva di affidabilità pubblicata.

**Secondarie:** tasso di successo per fascia; percentili di latenza p50/p95/p99
della decisione; conteggio dei nulli con ragione.

**Esplorativa (etichettata come tale per sempre):** ECE dopo ricalibrazione
split-half (fit su metà, valutazione sull'altra metà, mai sul tutto).

## 5. Baseline, dichiarate prima

- **B0** — predittore costante al tasso base: «la calibrazione da sola non basta».
- **B1** — soglia fissa 0.9 sulla confidenza grezza: «il calibratore aggiunge qualcosa?».
- **B2** — confidenza casuale, stesso marginale (seed 42): «il segnale non è rumore».

L'affermazione è sostenuta solo se il sistema batte B0 e B2 sulla
discriminazione e non peggiora B1 sulla calibrazione.

## 6. Dimensione campionaria e regola di arresto

**n = 120 decisioni valide con ≥ 30 della classe minoritaria** (ereditato da
RUN1 §6: con AUC vera 0.80, IC95 ≈ ±0.10). Si continua finché entrambe le
condizioni sono soddisfatte, con **tetto dichiarato di 200**: se a 200 valide la
classe minoritaria è < 30, il run si ferma e si riporta il mancato raggiungimento
— non si sposta il traguardo dopo.

- **La regola di arresto è su `n`, mai sul risultato.** Nessun AUC prima di 120/30.
- Durante il run si guardano solo: integrità record, `model_id` stabile, VRAM
  sopra il floor, cadenza, tasso per fascia.
- Ogni analisi prima della soglia è esplorativa ed etichettata come tale.

## 7. Regole di esclusione, decise ora

Record **nullo** (conservato con la ragione, fuori dal denominatore) se e solo se:

1. l'engine solleva un errore (`RizzoBridgeError`, timeout, risposta malformata);
2. la VRAM libera scende sotto 2 GiB durante la decisione;
3. il `contract_digest` differisce da `twoonesys-run2-v1`.

Un cambio di `model_id` segmenta il run in due dataset (mai mescolati).
Nessun'altra esclusione è ammessa dopo il congelamento.

## 8. Cosa falsifica l'affermazione

- **IC95 dell'AUC contiene 0.5** a n=120 → la confidenza non discrimina.
- **AUC ≥ 0.70 ma ECE > 0.10** → discrimina ma non è calibrata: si pubblica la
  distinzione, non la metà che conviene.
- **Nessuna differenza fra le fasce** → il banco non produce varianza: il
  risultato non riguarda il sistema ma il banco.

**Il rapporto si pubblica in tutti e tre i casi.**

## 9. Il pilota da 20 — solo controlli meccanici

1. il controllo di indipendenza di §2.3;
2. il tasso di successo differisce fra le fasce (§3);
3. telemetria completa in ogni record: `model_id`, `vram_free_mib`, latenza,
   `selection_probability`, `contract_digest`, `label_source`, fascia, `n`.

**Dal pilota non si legge alcun AUC, alcun ECE, alcuna curva.**

## 10. Propensione

In questo run esiste una sola azione possibile per record:
`selection_probability = 1.0` e **nessuna stima off-policy è possibile** su
questi dati. Dichiarato qui, come RUN1 chiedeva.

## 11. Firma

```
data: 2026-09-21
commit: (il commit che introduce questo file congela il metodo)
```
