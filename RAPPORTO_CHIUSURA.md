# Rapporto di chiusura — conoscenza + tecnologia

**Data:** 2026-09-21  
**Organo:** `01_PROGETTI/TWOONESYS`  
**Verdetto:** cerchio E2E conoscenza+tecnologia **chiuso**; generalizzazione
operativa sul mondo reale **SOSTENUTA**
(`bridge/RAPPORTO_GENERALIZZAZIONE.md`, gate G1–G8).

Limiti restanti (dichiarati, non nascosti): n=24 e tre reparti ≠ tutto il
support; fenomeni PCT effect_flip/catastrophe osservabili ma non
ancora rilevati a scala; ferita K10 (valore senza verdict) fuori batteria gen.

---

## Due pilastri, una filiera

| Pilastro | Cosa | Dove |
|---|---|---|
| **Tecnologia** | System One locale: decide → raw conf → detector → M4 → policy → exec → receipt → outcome | `engine/` + `harness/` + `bridge/` |
| **Conoscenza** | PCT: ScalaCosti + ordine temporale → episodi misurabili → consiglio stato futuro | `pct/` + `bridge/episode_contract.py` |

Fusi, non accostati:

```
ticket
  → engine (raw conf resta visibile)
  → detector testuale vs strutturale
  → M4
  → policy / execution / receipt
  → observed outcome
  → episodio (outcome_contract + tempi T0→T6)
  → PCT detector
  → stato futuro (conserva episodi / aggregato / non concludere assenza)
```

---

## Misura di chiusura (2026-09-21, engine 4B ready)

Eseguito: `python bridge/e2e_chiudi.py`

| | raw | M4 testuale | M4 strutturale | outcome |
|---|---:|---:|---:|---|
| A ledger vuoto | 1.000 | 1.000 | **0.536** | `LEDGER_EMPTY_CORRECT` |
| B ledger pieno | 1.000 | 1.000 | **1.000** | `OUTSIDE_DENIED_OK` |

Kill suite: **9/10 regge**, **1 ferita** (`K10`: valore attaccato senza `verdict` — detector troppo permissivo; lasciata onesta, non ritunata via).

PCT sugli episodi nuovi (n=2):

- `outcome_contract` + `outcome_magnitude` + tempi T0→T3: **2/2**
- **CATASTROPHE osservabile** (scala dichiarata) — prima era cieca sul log CASCADE
- EFFECT_FLIP / DRIFT: ancora non osservabili a questa scala (n piccolo) — **non** concluso come assenza

Stato futuro dichiarato dal run: *non concludere assenza — continua a scrivere episodi*.

---

## Cosa chiude questo

1. I **due campi** che l’audit PCT chiedeva alla sorgente sono nel percorso vivo:
   - `ScalaCosti` versionata (`twoonesys-billing-v1`)
   - ordine `condition_observed` < `action_chosen` (collider rifiutato)
2. L’outcome osservato non muore nel log booleano: ha **magnitudine dichiarata**.
3. PCT non è più cieco *per costruzione* su CATASTROPHE (scala presente).
4. Kill suite: domanda cattiva — *quanto costa mentire al sistema?* — non 100× Maria Rossi.

## Cosa NON chiude / limiti onesti

- n=24 e tre reparti: generalizzazione **operativa** sì (gate pre-registrati);
  non è una prova su tutto il traffico support.
- Che effect_flip / catastrophe *esistano* nel tuo traffico: ora sono
  **osservabili** se ci sono. Assenza ≠ non osservabile.
- PRISM come prodotto separato: etichetta futura, non pezzo vivo.
- Documents\\pct: non espanso; casa = `TWOONESYS/pct`.
- K10 (attached senza verdict): ferita nota del detector, non ritunata via.

---

## Come riprodurre

```
bridge\AVVIA_ENGINE.bat     # se :8017 non e' ready
bridge\AVVIA_E2E.bat        # cerchio completo + kill suite
```

Oppure pezzi:

```
python bridge/kill_suite.py
python bridge/e2e_chiudi.py
python bridge/adapter_episodi.py bridge/run_e2e/episodes.jsonl
```

Output: `bridge/run_e2e/e2e_summary.json`, `episodes.jsonl`, `kill_suite.json`.

---

## Lezione da non nascondere

`raw conf: 1.0000` resta in chiaro. Il motore può essere certo al 100%;
il mondo può non confermare la premessa. Tutto ciò che viene dopo il motore
esiste per quello.

---

## Comando operativo

| Domanda vecchia | Domanda nuova |
|---|---|
| TWOONESYS sa funzionare? | Quanto è difficile convincerlo che il mondo dice ciò che non dice? |

La prima è chiusa dal demo. La seconda è il banco permanente (`kill_suite`).
