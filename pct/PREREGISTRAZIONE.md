# PCT — pre-registrazione dell'esperimento §9

**Congelata il:** 2026-09-18, prima del run definitivo (`--seed 20260918`).
**Perimetro:** solo il mondo sintetico. Nessun dato reale, nessun LLM.

## 1. L'unica affermazione

> Rendere disponibili precedenti episodici produce decisioni migliori che
> rendere disponibile solo l'aggregato **pesato per propensione**, a parità di
> policy, budget, stati e azioni eleggibili.

## 2. I bracci

| | evidenza fornita alla stessa policy |
|---|---|
| P0 | niente |
| A | aggregato `(stato, azione) → Hájek, ESS, n` |
| C | regressione pesata su `(stato, d, e, d·e)`, senza interazione stato×ambiente |
| B | episodi con il record della carta §10.1 |

La policy è **un solo file** condiviso. Se differisse fra i bracci, il run è nullo.

## 2bis. Registro delle revisioni della predizione — leggere PRIMA della §3

**Questa pre-registrazione e' stata ristretta dopo aver visto dei dati, e va
detto qui, in testa, non in nota.**

| quando | predizione | fonte |
|---|---|---|
| spec §9, prima di qualunque run | B vince in **4** regimi: `confound`, `effect_flip`, `env_change`, `catastrophe` | ragionamento |
| dopo i run esplorativi (seed 101, 4242) | ristretta a **2**: `effect_flip`, `catastrophe` | dati osservati |
| run definitivo (seed 20260918) | 2 su 2 dei regimi ristretti | — |

**Il punteggio onesto e' quindi 2 su 4 rispetto alla predizione originale**, non
"2 su 2". Restringere l'insieme delle ipotesi dopo aver guardato i dati e poi
segnare contro l'insieme ristretto e' la stessa patologia dell'arresto opzionale,
applicata alle ipotesi invece che alla dimensione campionaria — ed e' esattamente
cio' che questo progetto esiste per non fare.

Le due che sono cadute, e perche':

- **`confound`**: contro un aggregato *forte* (gia' pesato per propensione) il
  confondimento e' corretto anche in A. La predizione originale immaginava un
  aggregato ingenuo.
- **`env_change`**: il fold di struttura precede interamente il cambio, quindi
  non puo' scoprire che `e` conta. E' un limite del protocollo a fold congelati.

Da qui in avanti, qualunque ulteriore restrizione va aggiunta a questa tabella
prima del run a cui si applica.

## 3. Le predizioni, dichiarate prima

| fenomeno | atteso |
|---|---|
| effect_flip | **B vince** — condizione osservabile che inverte l'effetto |
| catastrophe | **B vince** — coda pesante concentrata in un livello della condizione |
| nessuno, confound | pari — contro un aggregato *forte* la propensione basta ad A |
| drift | pari — regime che cambia senza marcatore osservabile; vederlo richiederebbe una pesatura per recency, vietata dalla carta §7 |
| env_change | pari — il fold di struttura precede il cambio, quindi non può scoprire che `e` conta. È un **limite del protocollo a fold congelati**, riportato come tale |
| sparse, low_support, delay | pari |

**Un vantaggio di B fuori da questa lista è un risultato INATTESO e va indagato
prima di essere pubblicato**, non festeggiato.

## 4. Metriche

Primaria: **rimpianto** contro l'azione ottima vera, differenza **appaiata** con
IC95 bootstrap (2000 ricampionamenti) sulle differenze per episodio.
Secondarie: catastrofi attese, tasso di `NO_EVIDENCE`, condizioni ammesse,
byte conservati, latenza di query, tempo di rebuild.

## 5. Il criterio, che non è una percentuale scelta

La soglia «≥30%» della spec era arbitraria. È sostituita da un **pareggio** nelle
unità dichiarate in `report.py`:

```
beneficio = (rimpianto_A − rimpianto_B) × n_episodi × VALORE_UNITA_RIMPIANTO
costo     = ΔMiB × COSTO_PER_MIB + Δms × COSTO_PER_MS
```

B è giustificato in un regime **solo se beneficio > costo** in quel regime.

## 6. Cosa falsifica

- B non vince in `effect_flip` **e** `catastrophe` → ipotesi non sostenuta.
- B vince ovunque e uniformemente → sospetto vantaggio di implementazione.
- Il pareggio non si raggiunge in nessun regime → il progetto è una tabella.
- Il vantaggio svanisce al crescere di n anche nei regimi non stazionari
  (`scaling.py`) → correttivo per piccoli campioni, non architettura.

## 7. Regole di igiene

- Seed del run definitivo: **20260918**, diverso da quelli usati durante lo
  sviluppo (101, 4242), perché quei fold di valutazione sono già stati visti.
- Tre fold: struttura `[0,40%)`, stima `[40%,80%)`, valutazione `[80%,100%]`.
  La valutazione si apre una volta sola.
- Il cancello di mutazione (`mutations.py`) deve essere **7/7** prima del run.
- Il rapporto si pubblica **qualunque sia il risultato**.
