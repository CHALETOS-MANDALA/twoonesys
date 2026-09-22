# PCT — audit prima del congelamento

**Data:** 2026-09-18
**Metodo:** eseguito, non letto. Ogni numero qui sotto viene da un comando girato
oggi; dove non ho potuto eseguire, è scritto che non ho potuto.
**Verdetto in una riga:** l'esperimento §9 è end-to-end e congelabile. Il
**progetto** PCT non lo è, e non deve esserlo: la sua domanda principale
è ancora senza risposta nel mondo reale, per mancanza di dati.

---

## 1. Cosa è verde, e come è stato verificato

| | esito | comando |
|---|---|---|
| Suite | **100 test passati** | `python3 -m pytest -q` |
| Cancello di mutazione | **7/7 uccise (100%)** | `python3 mutations.py` |
| Tabella del README riprodotta | identica | `report.py --episodes 200000 --seed 20260918` |
| Stub / mock / placeholder / TODO | **nessuno** | ricerca su tutti i `.py` |
| Import orfani | **nessuno** (5 rimossi in questo audit) | analisi AST |
| Dipendenze | solo `numpy` | — |

La suite è stata girata **anche sulla macchina di Rubinho**: 84 + 9 test verdi in
due invocazioni (il limite di 120 s della shell remota impedisce un'unica corsa).

---

## 2. L'affermazione misurata, e solo quella

> Rendere disponibili precedenti episodici produce decisioni migliori che rendere
> disponibile solo l'aggregato **pesato per propensione**, a parità di policy,
> budget, stati e azioni.

Misurata su nove regimi, seed `20260918` mai usato in sviluppo:

```
fenomeno          P0   A aggr  C param   B prec   B vs A
effect_flip   0.2291   0.0637   0.0607   0.0172   +73.0%   <- vince
catastrophe   0.2165   0.0449   0.0724   0.0120   +73.3%   <- vince
nessuno       0.1864   0.0099   0.0092   0.0099    +0.0%
confound      0.1864   0.0089   0.0091   0.0089    +0.0%
env_change    0.2803   0.0690   0.0544   0.0752    -9.1%
drift         0.2263   0.0110   0.0103   0.0110    +0.0%
sparse        0.1267   0.0110   0.0105   0.0110    +0.0%
low_support   0.1864   0.0139   0.0135   0.0139    +0.0%
delay         0.1036   0.0200   0.0206   0.0215    -7.4%
```

**Due regimi su nove**, e il pareggio costo/beneficio è raggiunto solo lì.

### 2.1 Il punteggio onesto è 2 su 4, non 2 su 2

La predizione originale (spec §9) elencava **quattro** regimi vincenti. È stata
ristretta a due **dopo** aver visto run esplorativi sui seed 101 e 4242, e il run
finale è stato poi giudicato sull'insieme ristretto. È la patologia
dell'arresto opzionale applicata alle ipotesi. Il registro completo è in
`PREREGISTRAZIONE.md` §2bis; qui basti che il numero da citare è **2/4**.

---

## 3. Difetti trovati eseguendo, in questa sessione

Tutti da un comando, nessuno da una rilettura del codice.

| # | difetto | come è emerso | stato |
|---|---|---|---|
| 1 | `effect_flip` era **inerte**: modificava la fetta `e=1` mentre `e` restava 0 ovunque | primo run: numeri identici al caso base a quattro decimali | corretto |
| 2 | B **condizionava sempre**, violando la carta §4.2: peggiorava di suo su `confound` (0.0303 vs 0.0221) | confronto con A | corretto (`structure.py`) |
| 3 | `CATASTROPHE` non testava nulla: `a2` non era **mai** l'azione ottima apparente (0 stati su 6) | audit mirato | corretto |
| 4 | `DELAY` era rumore simmetrico, non credit assignment | lettura del blocco generato | corretto (orizzonte T+N) |
| 5 | La guardia di `Evidence` cercava chiavi testuali in un dizionario a **chiavi intere**: non poteva scattare | audit | corretto (controllo di tipo) |
| 6 | `Status.UNKNOWN` **non veniva mai emesso** | ricerca nei provider | corretto |
| 7 | Una mutazione **sopravviveva** perché il meccanismo era duplicato in due punti e ne rompevo uno solo | cancello di mutazione | corretto (un solo punto) |
| 8 | Un vantaggio di B era un **artefatto di clipping** (`p` troncata a 0.98) | verifica del perché la condizione veniva ammessa | corretto (tetto a 0.70) |
| 9 | `stability()` era scritta e **mai chiamata** dalla pipeline | audit | corretto + test che lo verifica |

Il numero 7 è il più istruttivo: senza il cancello avrei **rimosso un meccanismo
che funzionava**, convinto di essere rigoroso.

---

## 4. Cosa NON è dimostrato — e va riletto prima di citare qualunque numero

1. **Non è dimostrato che funzioni nel mondo reale.** È dimostrato che
   l'informazione episodica vale in un mondo dove certi fenomeni esistono *per
   costruzione*.
2. **Non è validata una `state_key` reale.** Nel banco è data. `stability()`
   esiste per costruirla sui dati veri, ma non è mai stata girata su dati veri.
3. **Non è misurata alcuna latenza reale**: qui non c'è né solver né modello.
4. **`env_change` resta negativo**, ed è un limite del protocollo a fold
   congelati: la struttura precede il cambio d'ambiente e non può scoprirlo.
   Riportato, non aggirato.
5. **B accetta un rischio di coda** che A evita astenendosi ovunque. Il rimpianto
   lo include già, ma sotto un'utilità **avversa al rischio** (non lineare) la
   conclusione potrebbe cambiare. Non è stato provato.
6. **Nessuna misura su più seed.** Il run definitivo è uno. La variabilità fra
   seed non è quantificata.

---

## 5. Il mondo reale, misurato oggi

`adapter_cascade.py` su `cascade/run/lbp_calibration_100/outcomes.jsonl`, 67 record:

```
CONFOUND (segnale)               rilevato   0.1038
LOW_SUPPORT                      rilevato   1.0000
CATASTROPHE               non osservabile   nessuna scala di costi
EFFECT_FLIP               non osservabile   nessuna condizione pre-decisione
SPARSE / DRIFT            non osservabile   supporto insufficiente
```

E su `outcome_log.jsonl` (40 record): **una sola azione, propensione assente** →
nessuna diagnosi possibile, mai, per quei record.

**I due fenomeni in cui PCT ha mostrato valore sono oggi entrambi NON
OSSERVABILI sul log reale.** Non assenti: invisibili. È la conclusione più
importante di questo audit, e non dipende da quanto a lungo si faccia girare il
sistema: dipende da due campi che non vengono scritti.

`CONFOUND` è riportato come **segnale**, non come confondimento provato: una
divergenza fra media e Hájek è compatibile con selection bias, non lo dimostra.

---

## 6. Cosa serve alla sorgente — due campi, non venti funzioni

Validati in `contratto_sorgente.py`, con test:

- **scala dei costi dichiarata e versionata**: un booleano perde la differenza fra
  «ritenta» e «hai corrotto lo stato». `ScalaCosti` non ha default e solleva su un
  esito non dichiarato — un valore assegnato dopo il fatto è la stessa patologia
  dell'ipotesi ristretta dopo aver visto i dati;
- **ordine temporale verificabile**: `T0 condition → T3 scelta`. Un campo nato da
  `T4` in poi è un collider, e `valida_condizioni` lo rifiuta. Un campo che non
  dichiara la propria fase viene rifiutato allo stesso modo: senza quella
  dichiarazione non si *può* sapere se è pre-decisione.

`escalated` **non** è stato usato come condizione: non si sa chi lo scrive né
quando.

---

## 7. Debiti noti, piccoli e dichiarati

| | |
|---|---|
| `detector.py` non ha test propri oltre a quello sui tre stati | il resto è coperto indirettamente dall'adattatore |
| `scaling.py` non ha test | è uno script di misura, non una libreria |
| `_bytes_retained` stima la dimensione dell'indice, non la misura | dichiarato nel codice |
| La cartella non è un repository git | come `cascade/`: mezz'ora, e vale più di una feature |

---

## 8. Verdetto

**L'esperimento §9 è congelabile.** Ha una domanda sola, un criterio scritto
prima, un cancello di mutazione al 100%, un risultato riproducibile da un comando,
e un elenco esplicito di ciò che non dimostra.

**Il progetto PCT non è concluso**, e chiuderlo adesso in un senso o
nell'altro sarebbe una risposta inventata. Ciò che manca non è codice: sono due
campi alla sorgente e del tempo di macchina. Dopo quelli, succederà una delle due
cose che è giusto lasciar succedere — o i fenomeni per cui PCT ha mostrato
valore ci sono davvero nel dominio, o non ce ne sono abbastanza. **Entrambe sono
risposte vere**, e nessuna delle due si può avere oggi.
