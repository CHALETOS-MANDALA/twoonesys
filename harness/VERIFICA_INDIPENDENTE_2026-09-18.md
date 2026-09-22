# Verifica indipendente — cascade v1

**Data:** 2026-09-18
**Metodo:** moduli e test copiati in container pulito (Linux, numpy/z3/hypothesis, **senza torch**),
eseguiti da me. Nessuna affermazione qui viene dal tuo riepilogo.

---

## 1. Quello che ho confermato

| Affermazione | Esito |
|---|---|
| suite stabile, run ripetibili | **confermato** — 167/167 sui moduli nuovi, tre esecuzioni consecutive identiche |
| il guard Z3 chiude i due fail-open | **confermato, provato** (§2) |
| conformal implementata correttamente | **confermato** — `k = ceil((n+1)(1-α))`, k-esima statistica ordinata |
| separazione assessment / autorizzazione / esecuzione | **confermato** nei contratti |
| `Indeterminate` gestito | **confermato** — `outcome: bool \| None`, "non conta come successo NÉ come fallimento" |
| nessun numero inventato a freddo | **confermato** — `measured_p: float \| None`, "None = nessuna misura, mai un numero" |

**Nota sul mio primo controllo:** avevo scritto "due run DIVERSE". Era un errore mio — stavo
confrontando anche il tempo di esecuzione (0.91s vs 0.86s). Ripetuto sul conteggio: 167, 167, 167.

### Il guard, provato caso per caso `ESEGUITO`

```
coerente, rispetta                         -> RULES_VERIFIED
coerente, viola                            -> VIOLATION
binding mancante                           -> MISSING_BINDING
premesse contraddittorie (v==30 ∧ v==90)   -> INVALID_CONTEXT
solver che risponde unknown                -> INDETERMINATE

stati possibili: RULES_VERIFIED, VIOLATION, INVALID_CONTEXT, MISSING_BINDING, INDETERMINATE
solo RULES_VERIFIED autorizza
```

Entrambi i fail-open sono chiusi, compreso quello introdotto dalla **mia** correzione (la prova
vacua per premesse contraddittorie). `solver_check` è iniettabile, quindi `unknown` è testabile
davvero e non solo in teoria.

---

## 2. Il difetto reale: la barriera respinge il 50% dei claim VERI

`claim_barrier._digits_are_prefix` non fa un confronto per cifre. Fa un confronto
sull'**espansione binaria** del float:

```python
i_exp, f_exp = _split_digits(format(float(declared), f".{safe}f"))
cmp_f = format(float(declared), f".{safe}f").split(".", 1)[1][:window]
return cmp_f == f_dec[:window]
```

`float("143.1118")` non è rappresentabile in binario. La sua espansione reale è:

```
143.11179999999998813109
     ^ troncando a 4 decimali si ottiene '1117', non '1118'
```

Quindi un claim **fedele** viene respinto. Misurato su 2000 claim generati come troncamento
**esatto** delle cifre attese:

```
precision= 4   claim veri RESPINTI:  965/2000 = 48.2%
precision= 6   claim veri RESPINTI:  995/2000 = 49.8%
precision= 8   claim veri RESPINTI:  968/2000 = 48.4%
precision=10   claim veri RESPINTI: 1010/2000 = 50.5%
```

**Circa metà.** Dipende solo da quale lato dell'errore di rappresentazione cade il valore.

**Perché la suite è verde:** i due valori delle fixture cadono dal lato favorevole.
`float("14.1347")` = `14.13470000000000048601` — espansione **sopra**, troncamento corretto.
Con `143.1118` sarebbe caduta. È lo stesso schema del buco Z3: la suite esplora pochi valori, e
il difetto vive nella rappresentazione, non nella logica.

**Doppio danno.** Oltre al falso negativo, `float64` porta ~15-17 cifre significative: i 40
decimali del CalcKernel — il motivo per cui la barriera di `matematica` esisteva — non sono
verificabili in nessun caso. `precision=40` è accettato come campo ma non può essere onorato.

**La causa sta nel tipo:** `NumericClaim.value: float`. Un valore che deve essere confrontato
*per cifre* non può passare da un binario a virgola mobile.

**Correzione:** `value: str` (o `Decimal`), confronto stringa-contro-stringa dopo
normalizzazione, `float()` mai nel percorso di verifica. `matematica` lo faceva già così — è una
regressione rispetto all'originale, non un difetto ereditato.

Test da aggiungere (cade oggi, deve passare dopo):

```python
def test_prefisso_fedele_sempre_accettato():
    exp = "143.1118458076206327394051238689139299662"
    for p in (4, 8, 15, 25, 39):
        assert _digits_are_prefix(exp[: exp.index(".") + 1 + p], exp, p)
```

---

## 3. Tre campi mancanti nel log degli esiti

`OutcomeRecord` registra: `request_id, action, raw_confidence, measured_p, escalated, approved,
outcome, touched, version`.

Mancano tre cose che i documenti indicavano come obbligatorie:

| Manca | Conseguenza |
|---|---|
| **propensione** (`selection_probability`) | niente IPS / doubly-robust: non potrai valutare offline una politica che non hai eseguito, e i dati dell'esplorazione ε restano distorti |
| **`contract_digest`** | un calibratore stimato su questo log non si invalida quando cambiano scorer, schema o indice |
| **`label_source`** (MECCANICO/UMANO/COMPORTAMENTALE) | `outcome: bool` non dice *chi* ha stabilito la verità: una curva sola mescola classi di affidabilità diverse |

`escalated: bool` è un proxy grosso di `chosen_stage`, e non basta a ricostruire la propensione.

Sono tre campi, non tre moduli — ma vanno aggiunti **prima** di raccogliere dati, perché un log
senza propensione non è recuperabile a posteriori.

---

## 4. Conformal: quanti campioni servono davvero

La quantile è corretta. Ma ho misurato la **dispersione** su 200 estrazioni indipendenti del
calibration set (α = 0.10, K = 4):

```
n=  9   media=89.4%   p05=69.4%   min=42.9%
n= 25   media=92.4%   p05=82.5%   min=76.6%
n=100   media=90.3%   p05=84.4%   min=80.6%
n=300   media=89.8%   p05=86.4%   min=85.0%
```

La garanzia è **marginale anche sul calibration set**: vale in media sulle estrazioni, non per
quella singola che hai in mano. A n=9 la media è giusta ma la tua copertura reale può essere 43%.

Da leggere così: **~100 è la soglia perché la media sia giusta; ~300 è dove il caso peggiore
smette di essere imbarazzante** (85% invece di 43%). Il fatto che a n=300 la copertura stia sotto
il 90% nella metà delle estrazioni è atteso e corretto — conta *quanto* sotto, non *quante volte*.

Una cosa fatta bene: `k > n` restituisce `+inf`, cioè "troppi pochi punti → non respingere mai".
Degrada verso il conservativo invece di dare una garanzia falsa.

---

## 5. Due osservazioni minori

**`run/` è vuoto.** Dici "40 esiti reali persistiti" e "pulito": se lo smoke ripulisce alla fine,
la prova dei 40 esiti non esiste più su disco. Per un progetto la cui tesi è *nessun claim senza
evidenza*, lo smoke dovrebbe lasciare la **propria ricevuta** — un file di riepilogo firmato, non
il log intero. Altrimenti "40 esiti persistiti" è esattamente il tipo di affermazione non
verificabile che il sistema esiste per impedire.

**`test_workers.py` va in errore in raccolta** (qui) con
`BackendUnavailable: prism.geometry non importabile in-process`, sollevata da `workers.py:166`.
Sul tuo PC PRISM c'è, quindi passa. Ma un backend opzionale assente deve produrre uno **skip**,
non un errore di collection: così com'è, il conteggio "263 test" dipende dall'ambiente, e su una
macchina senza PRISM la suite non parte proprio.

---

## 6. Verdetto

Il grosso regge, ed è la prima volta in questa conversazione che un pezzo di codice supera i
casi avversariali che ho scritto per romperlo: il guard Z3 li passa tutti e cinque.

Resta **una cosa da correggere prima di raccogliere dati** — `value: float` nella barriera, che
respinge metà dei claim veri — e **tre campi da aggiungere al log** prima che il log cominci a
riempirsi, perché la propensione non si recupera dopo.

Nessuna delle due tocca l'architettura. Sono un tipo e tre campi.
