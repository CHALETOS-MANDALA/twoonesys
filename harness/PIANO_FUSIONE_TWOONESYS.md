# PIANO DI FUSIONE — Rizzo Flow × CASCADE → **TWOONESYS**

**Data:** 2026-09-21
**Stato:** piano approvato, nome scelto dall'utente: **TWOONESYS**
(in lavorazione erano: SINAPSI, LEGA, ARBITRO — scartati)
**Regola madre:** un organo = un solo percorso canonico (AGENTS.md). Gli spostamenti
seguono il metodo **sposta + junction + registro**.

---

## Avanzamento (aggiornato 2026-09-21 sera)

| Fase | Stato | Prova |
|---|---|---|
| 1 · Casa canonica | **FATTO** | `01_PROGETTI/TWOONESYS/{engine,harness,bridge}`; junction attiva al vecchio percorso di cascade; 2 righe in `mosse.jsonl`; porta 8017 registrata in `ports.yaml` (`twoonesys_engine`); repo radice `git init` (commit 4c6cdcf); harness aveva `.git` senza commit → primo commit b152ef3 (B7 chiuso davvero) |
| 2 · Engine install | **FATTO (1.7B)** | `uv sync --locked --extra cuda` OK; `auto_selects: cuda`; Spark-X2.5-**1.7B** Q8 scaricato e servito su :8017 (scelta utente: test di funzionamento prima di liberare disco per il 4B). VRAM: fermato qwen2.5:7b di Ollama (4,6 GB; si ricarica da solo al prossimo uso) → 7,2 GB liberi |
| 2b · Smoke live | **FATTO** | `bridge/smoke_live.py`: health con hash dei pesi ✓, proposta choice `billing` p=0,9990 (0 token generati) ✓, giro harness completo con record ✓. Prima chiamata 93 s (compilazione kernel, documentato), poi ~40 ms/decisione. Il gate ha **correttamente rifiutato** l'azione (nessuna evidenza numerica dal kernel): la tesi «decisione ben formata ≠ permesso» dimostrata in esecuzione |
| 3 · Bridge | **FATTO (codice)** | `harness/rizzo_bridge.py` + `run_with_rizzo()` in `integrated_workflow.py` + 9 test (`tests/test_rizzo_bridge.py`), suite completa **349 passed, 2 skipped**. Nota: il modulo vive dentro l'harness (come `latent_bridge.py`), `bridge/` tiene i documenti — vedi `bridge/README.md` |
| 2c · **Primo test reale** | **FATTO** | `bridge/real_test.py`, tre bracci dal vivo. **A**: engine decide `billing` p=0,9994 (0 token) → scrittura in sandbox → `authorized=True, outcome=True`, ricevuta firmata e verificata con sole chiavi pubbliche. **B**: STESSA decisione, path fuori sandbox → `authorized=False`, file mai creato, ricevuta di rifiuto verificata — p=0,9994 non ha mosso la policy. **C**: engine sceglie `14.1347` → claim contro evidenza zeron calcolata dal kernel → `verdict.ok=True, claim_ok`. Patch bridge: per `numeric` il claim e' l'ancora scelta (argmax), non la media pesata |
| 4 · Tre proponenti | da fare | — |
| 5 · La misura | **RUN2→RUN8 + E2E + GEN** | Catena calibrazione; detector; E2E conoscenza+tecnologia; **generalizzazione mondo reale SOSTENUTA** (G1–G8, n=24). `RAPPORTO_GENERALIZZAZIONE.md`. |
| 6 · Identità | **cablato in SIX-IDE** | Faccia :1420 ↔ gate :8018 ↔ engine :8017. Effect tools + triage chat + episodi. Doc: `CABLAGGIO_SIX.md`. Soft-bypass se freio spento. |

---

## 0. Verifiche fatte (misurate, non supposte)

| Fatto | Esito | Come verificato |
|---|---|---|
| Limiter SIX (six_resource_limiter) | **ELIMINATO** — restano solo i documenti | `C:\RecoverX_SIX\tools\six_limiter` non esiste; porta 8020 non in ascolto; nessun scheduled task; nessuna voce in Run key |
| GPU | **RTX 5070 Laptop, 8151 MiB** | `nvidia-smi` |
| VRAM occupata ora | **7114 MiB** da LM Studio, Ollama (llama-server), TouchDesigner (MORPH_THE_FACE — congelato, non si tocca), Cursor | `nvidia-smi --query-compute-apps` |
| Toolchain | uv 0.12.10 · Python 3.11.9 · git 2.54 | versioni misurate |
| Porta 8017 (default Rizzo) | **libera** nel registro `C:\RecoverX_SIX\ports.yaml` (occupate 8010-8012, 8020-8025) | lettura registro |
| Albero canonico | `01_PROGETTI` esiste sotto `_MADRE_RUBINHO`, nessuna collisione col nome TWOONESYS | listing |
| Licenze | entrambe **Apache-2.0** — fusione lecita, NOTICE di Rizzo va preservato in `engine/` | LICENSE dei due progetti |

### Conseguenza VRAM

Il limiter non c'è più: budget reale = **8 GB fisici**. Il 4B Q8 chiede ~5 GiB:
**entra, ma non in convivenza** con LM Studio + Ollama caricati (7.1 GiB già presi).
Disciplina adottata (stessa logica dei `profiles` già in ports.yaml):

- **Run di misura / banco**: scaricare il modello da LM Studio e `ollama stop` → 4B Q8 libero.
- **Uso sempre acceso** (se servirà): valutare 1.7B Q8 (~2.8 GiB), sapendo che è molto
  meno accurato (documentato: 0.700 vs 0.829 su authored144) e va usato con
  `allow_abstain: false`.
- **BF16 escluso** su questa GPU: ~8-10 GiB, non entra. Q8 è la precisione canonica qui.

---

## 1. Cosa diventa

Dopo la fusione non è più un modello (Rizzo) e non è più un harness (CASCADE).
Diventa **il primo System One completo e locale**:

> **una proposta entra, viene decisa con probabilità reale, passa un cancello di
> evidenza e policy, viene autorizzata o bloccata, l'esito è osservato, e tutto
> lascia una ricevuta firmata verificabile da terzi.**

Jev copre la decisione. CASCADE copre l'autorizzazione. TWOONESYS copre
**decisione → autorizzazione → prova**, su hardware proprio, senza fornitore.

### Il nome

**TWOONESYS** — etimologia dell'utente, 2026-09-21:

> Rizzo è un System One **modello**. CASCADE è un System One **harness**.
> Due System One → un sistema solo: **TWO · ONE · SYS**.

Due piani — quello decisionale e quello di autorizzazione — che i documenti
tenevano separati diventano un organo solo. E dentro il nome sta già scritto il
programma: **ONE SYS** = System One, completo.

---

## 2. Architettura finale

```
agente (SIX, CELL, qualunque)
   │  proposta
   ▼
TWOONESYS/engine   (Rizzo Flow, :8017)
   │  decisione tipizzata + probabilità REALE dai logit, 0 token generati
   ▼
TWOONESYS/bridge   (adattatore nuovo, ~80 righe)
   │  raw_confidence = p(opzione) · action_chosen = opzione ·
   │  model_value = primitiva numeric · status≠ok → escalation forzata
   ▼
TWOONESYS/harness  (CASCADE)
   │  ReliabilityMeter → gate 1-α → Z3 RULES_VERIFIED →
   │  permit + grant anti-TOCTOU → esecuzione → esito osservato
   ▼
ricevuta firmata cascade.receipt.v1 — verificabile con sola chiave pubblica
```

---

## 3. Le fasi

### Fase 1 — Casa canonica (sposta + junction + registro)

```
01_PROGETTI/TWOONESYS/
├── engine/    ← rizzo-flow-main (da Downloads)
├── harness/   ← cascade/ (da Documents\New OpenCode Project)
└── bridge/    ← nuovo
```

1. `git init` nella nuova radice (risolve il bug B7: cascade oggi non è un repo).
2. Spostare `C:\Users\andre\Downloads\rizzo-flow-main\rizzo-flow-main` → `engine/`.
3. Spostare `C:\Users\andre\Documents\New OpenCode Project\cascade` → `harness/`,
   poi **junction** al vecchio percorso (`New-Item -ItemType Junction`) così i
   comandi e i `.bat` esistenti continuano a risolvere.
4. Registrare lo spostamento in `01_PROGETTI/SIX_MADRE/00_INVENTARIO/PIANO_RIORDINO.md`.
5. Registrare la porta in `C:\RecoverX_SIX\ports.yaml`:
   `id: twoonesys_engine · port: 8017 · owner: TWOONESYS · health_path: /health`.
   Nota di pulizia: la voce `six_resource_limiter` (8020) è orfana — il codice non
   esiste più; marcarla `status: removed` (decisione dell'utente, è il suo registro).
6. Reinstallare il pacchetto dal nuovo percorso: `pip install -e harness/`.

### Fase 2 — Engine: installazione e primo boot

```powershell
cd 01_PROGETTI/TWOONESYS/engine
uv sync --locked --extra cuda
.venv\Scripts\activate
rizzo download                 # Spark-X2.5-4B, ~8 GB in models/
# disciplina VRAM: scaricare il modello da LM Studio, `ollama stop`
rizzo serve --bits 8           # → http://127.0.0.1:8017
```

Verifica: `GET /health` (riporta provenienza e hash dei pesi), poi una chiamata
fumo a `POST /v1/systemone`. La prima richiesta compila i kernel GPU (~1 min),
poi ~90-300 ms/decisione a caldo.

### Fase 3 — Bridge: l'adattatore (il codice nuovo)

`bridge/rizzo_proposer.py`, specchio di `harness/latent_bridge.py`:

- `RizzoProposer.propose(state: dict, questions: dict) -> RizzoProposal`
  via httpx (pattern già in `ollama_router.py`) su `:8017/v1/decisions`.
- Mappatura nel workflow (`run_with_rizzo()`, copia di `run_with_latent_brain`):

| Campo CASCADE | Sorgente Rizzo |
|---|---|
| `raw_confidence` | probabilità dell'opzione scelta (segnale vero: oggi è 0.5 cablato o coerenza saturata) |
| `action_chosen` | il `choice` — **identità del braccio** (risolve B3: IPS/doubly-robust diventano usabili) |
| `model_value` | primitiva `numeric` (valore pesato + spread) — niente più regex su testo generato |
| escalation | `status: insufficient_evidence / uncertain` → System 2, **mai autorizzare un'astensione** |

- Test di conformità nuovo, sul modello di `test_eni_bridge.py`: bridge giù →
  errore tipizzato, mai un proseguimento di comodo.

### Fase 4 — Il test dei tre proponenti (JEV_VS_CASCADE §7)

Lo stesso contratto, **senza modifiche**, servito da:
1. TWOONESYS/engine locale (:8017),
2. Ollama generico (:11434, percorso già esistente),
3. (quando vorrai) Jev hosted — cambia solo la base URL.

Criterio di successo: ricevute verificabili in tutti i casi con
`python -m cascade verify receipt.json`. Se l'harness regge il cambio, la
separazione fra piano decisionale e piano di autorizzazione è proprietà osservabile.

### Fase 5 — La misura (ciò che mancava a CASCADE)

Il run di calibrazione da 250-300 record con prompt a varianza vera:
- con LBP costava ~62 s/record (~4 h) e la coerenza restava inchiodata a 1.0;
- con engine: **~0.1-0.3 s/decisione** → il run completo in minuti, e le
  probabilità si muovono davvero col prompt.
- Pubblicazione: AUC con intervallo + ECE/curva, ≥25-30 esiti della classe rara,
  contro le baseline dichiarate prima (PREREGISTRAZIONE_RUN1.md).

### Fase 6 — Identità

- README di TWOONESYS (cosa è, cosa non è, come si verifica una ricevuta).
- NOTICE aggregato (Apache-2.0 entrambi; pesi Spark dai loro repository).
- Questo piano resta in `harness/` come documento storico della fusione.

---

## 4. Onestà (i rischi, detti prima)

- **Probabilità peaked**: engine a volte dice 0.9999 e sbaglia (6 confident-wrong
  su 36 documentati dall'autore). Non è un difetto per TWOONESYS: è il caso d'uso
  del cancello — la confidenza grezza viene ricalibrata sugli esiti osservati e
  sotto soglia si escala. Ma va detto: la p di engine è un *segnale*, non una
  garanzia; la garanzia resta del harness.
- **Un modello residente, richieste serializzate**: va bene per un cancello, non
  per un servizio multi-tenant.
- **La VRAM è il vincolo fisico vero**: 8 GB totali, condivisione impossibile con
  lo stack ENI/LM Studio caricato. I profili di ports.yaml sono la disciplina.
- **Nessun numero finché non c'è il run**: la Fase 5 è la prima misura onesta del
  sistema fuso. Prima di quella, TWOONESYS è un'architettura verificata, non una
  misura.

---

## 5. Definizione di «fatto»

1. `01_PROGETTI/TWOONESYS` esiste, è un repo git, junction attiva, registro e porta
   registrati.
2. `rizzo serve --bits 8` risponde su `:8017/health` con 4B Q8.
3. `run_with_rizzo()` passa i test di conformità; un'astensione non viene mai
   autorizzata (test dedicato).
4. Il test dei tre proponenti produce ricevute verificabili.
5. Il run di misura è pubblicato, qualunque sia il numero.
