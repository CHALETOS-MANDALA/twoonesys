# PCT — esperimento §9

> **Casa canonica (2026-09-21):** `01_PROGETTI/TWOONESYS/pct`  
> Fuso come pilastro *conoscenza* con la tecnologia System One.  
> Vedi `CASA_CANONICA.md` e `../RAPPORTO_CHIUSURA.md`.

Mondo sintetico a verità nota per decidere **se conservare gli episodi valga più
che conservare l'aggregato**. Nessun LLM, nessun embedding, nessun database.
Unica dipendenza: numpy.

## Come si gira

```
python3 -m pytest -q          # 100 test
python3 mutations.py          # cancello di mutazione: deve essere 7/7
python3 report.py --episodes 200000 --seed 20260918
python3 scaling.py            # la predizione falsificabile sulla scala
python3 detector.py <log.jsonl> [campo_condizione]   # quanto fenomeno c'è nel reale
```

## I file

| | |
|---|---|
| `world.py` | il mondo, la verità, gli otto fenomeni a interruttore |
| `estimators.py` | Hájek, ESS, media semplice, LCB |
| `structure.py` | quali condizioni meritano di essere usate (DiD + stabilità + regola eventi rari) |
| `evidence.py` | il contratto, le guardie, `NO_EVIDENCE` / `UNKNOWN` |
| `policy.py` | **una sola** policy, condivisa da tutti i bracci |
| `evidence_agg.py` / `evidence_param.py` / `evidence_prec.py` | i bracci A, C, B |
| `runner.py` | tre fold, confronto appaiato, bootstrap |
| `report.py` | tabella per fenomeno, verdetti, pareggio costo/beneficio |
| `scaling.py` | il vantaggio al crescere di n |
| `detector.py` | rileva i fenomeni su un log reale |
| `mutations.py` | il cancello: una proprietà che sopravvive alla sua mutazione non è provata |

## Il risultato (seed 20260918, 200k episodi)

```
fenomeno          P0   A aggr  C param   B prec   B vs A
nessuno       0.1864   0.0099   0.0092   0.0099    +0.0%
confound      0.1864   0.0089   0.0091   0.0089    +0.0%
effect_flip   0.2291   0.0637   0.0607   0.0172   +73.0%   <-- B vince
env_change    0.2803   0.0690   0.0544   0.0752    -9.1%
catastrophe   0.2165   0.0449   0.0724   0.0120   +73.3%   <-- B vince
drift         0.2263   0.0110   0.0103   0.0110    +0.0%
sparse        0.1267   0.0110   0.0105   0.0110    +0.0%
low_support   0.1864   0.0139   0.0135   0.0139    +0.0%
delay         0.1036   0.0200   0.0206   0.0215    -7.4%
```

**Due regimi su nove.** La lettura onesta non è «pre-registrazione superata»: la
predizione originale (spec §9) elencava **quattro** regimi vincenti, ed è stata
ristretta a due *dopo* aver visto dati esplorativi. Il punteggio rispetto alla
predizione originale è quindi **2 su 4** — vedi il registro delle revisioni in
`PREREGISTRAZIONE.md` §2bis.

Quello che le due vittorie mostrano è più stretto e più utile: `effect_flip` e
`catastrophe` sono esattamente i casi in cui **l'aggregazione butta via
l'informazione che cambia la decisione**. Non «funziona ovunque»: «qui succede
qualcosa di diverso».

Il pareggio costo/beneficio è raggiunto solo in quei due regimi.

## Cosa questo NON dimostra

Non dimostra che funzioni nel mondo reale: dimostra che l'informazione episodica
vale in un mondo dove certi fenomeni ci sono **per costruzione**. Quanto ce ne sia
nel tuo dominio lo dice `detector.py`, sul tuo log — e il valore atteso è il
prodotto delle due metà.
