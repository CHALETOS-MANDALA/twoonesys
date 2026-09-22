# Prior art — TWOONESYS (ricerca 2026-09-21)

**Metodo:** ricerca mirata su paper + prodotti (non opinione). Ogni riga ha
una fonte. Verdetto in tre livelli: **NOTO** / **ATTIVO (campo caldo)** /
**COMPOSIZIONE RARA**. «Nuovo» assoluto non è un'affermazione sostenibile
senza un patent search professionale; ciò che segue è una mappa onesta.

---

## Tabella per asse

| # | Elemento TWOONESYS | Prior art più vicino | Anno | Verdetto |
|---|---|---|---|---|
| 1 | Temperature scaling globale (RUN4, T=3.947) | Guo et al., *On Calibration of Modern Neural Networks* (ICML) — ECE + T unico | 2017 | **NOTO** |
| 2 | Temperature per condizione / gruppo (RUN5) | *Dual Temperature Scaling* (arXiv:2310.10399); *GC+TS* NeurIPS 2023; **Multicalibration** Hébert-Johnson et al. ICML 2018 | 2018–2023 | **NOTO** (è *multicalibration / group-conditional TS*) |
| 3 | Engine decisionale tipizzato, 0 token (Rizzo) | TypeSafe **Jev** / System One (lancio ~15 set 2026); ricreazioni open: Rizzo Flow, jev-lite | 2026 | **ATTIVO** — categoria nuova di prodotto, non inventata da noi |
| 4 | Confidence-gated actions | Documentazione TypeSafe: *Confidence-gated actions* (soglie per azione; il codice circostante mantiene controllo e side effects) | 2026 | **NOTO** — vedi §2 sotto per la formulazione precisa del contrasto |
| 5 | Cancello pre-esecuzione + ricevute firmate | **Open Agent Passport** (arXiv:2603.20953); draft IETF **AgentROA**; `11-11AI/execution-governance`; ScopeGate; AgentLock | 2025–2026 | **ATTIVO** — campo esploso; CASCADE ci sta dentro, non fuori |
| 6 | Claim numerico vs oracolo indipendente | **Proof-Carrying Numbers** (World Bank / Solatorio, arXiv:2509.06902); QuantGuard; Anti-Lie | 2025 | **ATTIVO** — la barriera claim di CASCADE è strettamente affine a PCN |
| 7 | Astensione / evidenza insufficiente | Evidence Sufficiency Benchmark; GRAB-RAG; selective prediction + entropy insufficiency | 2022–2026 | **ATTIVO** — fascia C di RUN3 è un risultato *previsto* dalla letteratura |
| 8 | Memoria episodica vs aggregato + propensione | Off-policy / Hájek / importance sampling (RL classico); episodic RL (NeurIPS/IJCAI) | 2001–2021 | **NOTO** come pezzi; PCT come *esperimento §9* per gate è più specifico |
| 9 | Pre-registrazione + pubblicazione delle sconfitte | Clinical trials / open science; mutation testing | decenni | **NOTO** come disciplina — **raro** nei prodotti AI |
| 10 | **Filiera chiusa misurata**: System One locale + gate (policy ≠ confidenza) + claim barrier + calibrazione componibile + ECE/AUC pre-registrati pubblicati anche perdenti + ponte a memoria episodica | *Nessun prodotto trovato che chiuda tutti gli anelli* | — | **COMPOSIZIONE RARA** |

---

## Dettaglio delle scoperte che contano

### 1. RUN5 non è una scoperta teorica — è un'applicazione misurata

La letteratura chiama esplicitamente ciò che abbiamo fatto:

- Guo 2017: T globale (il nostro RUN4).
- Dual Temperature Scaling / GC+TS / Multicalibration: T per gruppo
  (il nostro RUN5). La frase «T globale è la media di due verità opposte»
  è la motivazione *stessa* della multicalibration: la calibrazione media
  può nascondere sottogruppi catastroficamente miscalibrati.

**Cosa è nostro:** averlo dimostrato *sul cancello decisionale locale*,
con oracolo indipendente, pre-registrazione, valutazione appaiata fuori
campione, e pubblicazione del fallimento di RUN4 prima del successo di
RUN5. La letteratura lo dimostra su ImageNet/CIFAR/fairness; noi su un
*authorization gate* con claim barrier. Dominio diverso, metodo ereditato.

### 2. TypeSafe è il concorrente più vicino — formulazione precisa

- Jev = System One commerciale (chiuso, waitlist, $40M seed DCVC).
- Documentano *confidence-gated workflows*: la confidence contribuisce al
  gating operativo; le fonti pubbliche dicono anche che è il **codice
  circostante** a mantenere controllo, threshold e side effects. Non
  affermare che «TypeSafe insegna il contrario» — è troppo forte rispetto
  a ciò che è verificabile.
- Glossario ECE: citano Guo 2017, e ammettono: **«TypeSafe has not published
  an ECE figure for Jev»** (verificato 2026-09-18 su systemonemodels.org).

**Formulazione inattaccabile del contrasto:**

> Jev documenta workflow in cui la confidence contribuisce direttamente al
> gating operativo. TWOONESYS implementa invece un contratto esplicito nel
> quale confidence e authorization policy rimangono assi indipendenti,
> permettendo alla policy di negare un'azione anche in presenza di
> confidence estremamente elevata.

Misura che sostiene il contratto: test reale braccio B (p=0.9994, scrittura
fuori sandbox → `authorized=False`, ricevuta di rifiuto verificata).
TWOONESYS ha inoltre ECE pubblicati (0.259 → 0.282 → 0.182 → **0.069**).

### 3. I cancelli con ricevute firmate esistono già (2025–2026)

Non siamo soli: OAP, AgentROA (IETF draft), execution-governance, ScopeGate,
AgentLock. Tutti fanno pre-action authorization + audit/receipts. La
differenza nostra non è «abbiamo inventato il gate» — è **gate + engine
System One calibrato misurato + claim barrier + disciplina del banco**.

### 4. La claim barrier ha cugini seri

PCN (World Bank, set 2025): verifica meccanica dei numeri nel renderer,
fail-closed, proof. QuantGuard / Anti-Lie: stessa filosofia. Il nostro
`run_verified` / claim barrier è *nella stessa famiglia*, non un'isola.

### 5. PCT

I pezzi (Hájek, ESS, off-policy, episodic vs semantic memory) sono noti.
Ciò che è più specifico: l'esperimento sintetico con interruttori
`effect_flip` / `catastrophe` *come giustificazione di un gate* e il
contratto sorgente (scala costi + ordine temporale). Non ho trovato un
prodotto che usi quel detector per decidere se un ReliabilityMeter deve
essere aggregato o episodico — ma un patent search serio andrebbe fatto
prima di qualsiasi claim di novità lì.

---

## Verdetto in una frase

> **I mattoni sono noti. Il campo del cancello è caldo (2025–2026). La
> filiera chiusa e auto-misurante — System One locale + policy separata dalla
> confidenza + claim barrier + calibrazione componibile con numeri pubblicati
> anche quando perdono + ponte a PCT — non ha un equivalente
> scaricabile trovato in questa ricerca.**

## Cosa NON affermare (e cosa sì)

| ❌ Non dire | ✅ Si può dire |
|---|---|
| «Abbiamo inventato la temperature scaling» | «Applichiamo Guo 2017 / multicalibration a un cancello decisionale, con misura pre-registrata» |
| «Abbiamo inventato le ricevute firmate» | «Siamo nella famiglia OAP/AgentROA, con un contratto di misura che loro non pubblicano» |
| «Nessuno ha System One» / «TypeSafe insegna il contrario» | «Jev esiste; Rizzo è open. Contratto: confidence e policy come assi indipendenti (vedi §2). ECE pubblicati da noi; TypeSafe non ha pubblicato ECE per Jev» |
| «Tecnologia 100% nuova» | «Architettura sperimentale coerente con proprietà di affidabilità misurabile end-to-end — non una raccolta di idee» |

## Limiti di questa ricerca

- Non è un patent search (EPO/USPTO). Non basare IP claims su questo file.
- Coverage di web/arxiv/GitHub, non di paper dietro paywall non indicizzati.
- Il campo «agent authorization» si muove a settimane: da rieseguire prima
  di pitch/fundraising/pubblicazione.

## Fonti principali (cliccabili)

1. Guo et al. 2017 — https://proceedings.mlr.press/v70/guo17a.html
2. Hébert-Johnson et al. 2018 Multicalibration — https://proceedings.mlr.press/v80/hebert-johnson18a.html
3. Dual Temperature Scaling — https://ar5iv.labs.arxiv.org/html/2310.10399
4. TypeSafe System One / Jev — https://typesafe.ai/blog/introducing-system-one-models-and-jev
5. TypeSafe ECE glossary (ammette ECE non pubblicata) — https://systemonemodels.org/glossary/expected-calibration-error/
6. Open Agent Passport — https://arxiv.org/html/2603.20953v1
7. AgentROA IETF draft — https://datatracker.ietf.org/doc/draft-nivalto-agentroa-route-authorization/00/
8. Proof-Carrying Numbers — https://arxiv.org/abs/2509.06902
9. execution-governance (signed receipts) — https://github.com/11-11AI/execution-governance
