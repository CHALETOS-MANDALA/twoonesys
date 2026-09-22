# Emendamento 2026-09-21 a PREREGISTRAZIONE_RUN2_TWOONESYS.md

Come la regola impone: il documento congelato (commit c16f872) non si tocca;
qui si dichiara cosa è cambiato e perché, **prima** del run vero.

## 1. Anchor in ordine crescente (scoperta del pilota)

Il primo pilota è stato **invalidato da un bug del banco, non del sistema**:
88 tentativi su 108 rifiutati con HTTP 422. Causa: lo schema dell'engine
(`engine/src/rizzo_flow/schema.py:82`) richiede anchor numerici
*strettamente crescenti*; il banco li mescolava per smorzare il bias di
posizione.

Decisione: gli anchor si inviano **ordinati per valore**; il mescolamento
anti-bias dichiarato in §2 del documento congelato **è ritirato** per la
primitiva `numeric` (l'ordine lì porta significato: è il supporto 1-D della
distribuzione). Il bias di posizione si mitiga diversamente: i valori dei
distrattori variano per record (perturbazione ±1 sull'ultima cifra, ±0.5,
zero adiacente), quindi la posizione dell'anchor corretto varia comunque
di record in record.

## 2. Candidati speciali BELOW/ABOVE

La primitiva `numeric` aggiunge sempre due candidati speciali («il valore è
sotto/sopra gli anchor»). Se l'engine li sceglie, il bridge produce
`model_value=None` → la barriera risponde `MODEL_VALUE_MISSING` →
`outcome=False`. Dichiarato qui: **mancanza di claim = fallimento**, non
nullo. È la lettura onesta: il sistema non ha prodotto la cifra richiesta.

## 3. Il primo pilota si butta

I 20 record validi del primo pilota sono stati raccolti attraverso un pattern
di richieste difettoso (solo le permutazioni casualmente ordinate passavano):
il campione è selezionato dal bug e non si usa. Il pilota **si riesegue da
zero** con il banco corretto. I controlli meccanici di §9 restano identici.

## 4. Invariato

Ipotesi, oracolo, fasce, soglie (120 valide / ≥30 fallimenti / tetto 200),
baseline, regole di esclusione, criteri di falsificazione: tutto come nel
documento congelato.
