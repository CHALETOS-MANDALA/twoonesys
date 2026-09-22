# Pre-registrazione — Run 7: migliorare la sopravvivenza senza rompere il laboratorio

**Stato: CONGELATA dal commit che introduce questo file.**

| | |
|---|---|
| Autore | Rubinho |
| Data | 2026-09-21 |
| Base | logit già raccolti (fit seed 42, eval seed 2026) — sola lettura |
| Domanda | Quale mappa di calibrazione migliora la curva di degradazione (ε) **senza** far scadere ECE/AUC sul detector pulito sotto le soglie di RUN5/6? |

---

## 1. L'unica affermazione da misurare

> Esiste almeno una mappa dichiarata in §2 che, sulla popolazione seed 2026:
> (a) con detector pulito: **ECE ≤ 0.10** e **AUC ≥ 0.70**, e
> (b) a ε=0.20 di contaminazione delle etichette/condizioni: **ECE ≤ 0.10**
>     **oppure** ECE strettamente minore di quello della mappa RUN6
>     (baseline dura: ECE 0.103 a ε=0.20),
> con AUC a ε=0.20 ≥ 0.85.

Se nessuna mappa soddisfa entrambi, l'affermazione cade e si pubblica il
Pareto: ogni mappa ha un punto (ECE_pulito, ECE_ε20, AUC_ε20).

## 2. Mappe dichiate (bracci appaiati, stessi logit, stessi esiti)

Tutte applicate harness-side. Fit solo sul seed 42.

| id | Nome | Come si ottiene T / condizione |
|---|---|---|
| **M0** | dura RUN6 | T_presente=T_A, T_assente=T_C (griglia estesa, NLL puro). Condizione hard. Baseline. |
| **M1** | T regolarizzata | Fit per fascia minimizzando `NLL + λ (log T)²`, λ ∈ {0.05, 0.1, 0.2, 0.5}. Si sceglie λ **prima** guardando solo il fit set (min NLL_reg sul fit; tie-break: T più vicino a 1). Condizione hard come M0. |
| **M2** | T vincolata | Come M0 ma T ∈ [0.2, 5.0] (clip della griglia). Condizione hard. |
| **M3** | astensione | Soft-score s sullo stato (dichiarato §2.1). Se \|s\| < τ=0.5 → T_globale (3.947). Altrimenti presente/assente con T di M0. |
| **M4** | soft | T(s) = exp( w·log T_assente + (1-w)·log T_presente ), w = σ(-k·s), k=2, T da M0. |
| **M5** | combo | Soft-score + astensione (τ=0.5) + T regolarizzata (λ scelto come M1). |

### 2.1 Soft-score (dichiarato, pre-decisione)

```
s = 0
s += 1.0  se truth_4dp compare nel rapporto
s += 0.5  se «valore confermato» compare
s -= 1.0  se «non disponibile» o «ancora in corso»
s -= 0.3  per ogni altro zero (truth di n'≠n) presente nel testo
```

Nessun accesso alla fascia oracolo.

### 2.2 Contaminazione (due regimi, entrambi riportati)

- **ε-label** (come RUN6): flip di frazione ε ∈ {0.05,0.10,0.20} dell'etichetta hard presente/assente (seed 7). Per M3/M4/M5 il flip agisce sull'etichetta effettiva usata (dopo soft/astensione si ri-applica il flip sulla condizione discreta risultante; per M4 soft puro si contamina s ← -s con prob. ε).
- **feature-drop** (nuovo): con probabilità δ ∈ {0.1,0.2} si nasconde il match di `truth_4dp` al detector (simula estrazione fallita). Seed 11. Misura quanto M3/M4 guadagnano quando il segnale lessicale manca.

## 3. Metriche

Primarie (decidono §1): ECE e AUC su pulito; ECE e AUC a ε=0.20.
Secondarie: accuratezza detector; tasso di astensione M3/M5; T fittate;
Pareto di tutte le mappe; feature-drop δ=0.2.

Controllo obbligatorio: M0 deve riprodurre RUN6 (ECE pulito ≈ 0.069, AUC 1.0).

## 4. Cosa falsifica

- M0 non riproduttibile → STOP.
- Nessuna mappa soddisfa §1 → affermazione non sostenuta; si pubblica il Pareto.
- Una mappa «vince» su ε=0.20 ma ECE pulito > 0.10 → non conta come successo (§1 richiede entrambi).

**Il rapporto si pubblica in tutti i casi.**

## 5. Invariato

Niente nuove chiamate all'engine. Niente modifiche a `run_twoonesys_run1.py`,
rapporti RUN2–6, pesi, o server. Script nuovo: `run7_eval.py`.

## 6. Firma

```
data: 2026-09-21
commit: (congelamento)
```
