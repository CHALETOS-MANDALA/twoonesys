# Rapporto — Generalizzazione sul mondo reale

**Data:** 2026-09-21  
**Metodo:** `PREREGISTRAZIONE_GENERALIZZAZIONE.md` (congelata **prima** del run)  
**Batteria:** `gen_cases.py` n=24  
**Engine:** ready, Spark-X2.5-4B Q8 `:8017`  
**Output:** `run_gen/summary.json`, `run_gen/outcomes.jsonl`

---

## Verdetto

# **AFFERMAZIONE SOSTENUTA**

Tutti i gate G1–G8 della pre-registrazione sono PASS.

---

## Gate

| Gate | Esito | Misura |
|---|---|---|
| G1 Routing | **PASS** | accuracy **0.9565** (22/23 gold chiari; soglia ≥0.75) |
| G2 Strutturale onesto | **PASS** | **1.00** (22/22 `expect_usable=False` → label False) |
| G3 Divergenza | **PASS** | 3/3 casi; Δ(M4_t−M4_s) = 0.467, 0.464, 0.472 (≥0.20) |
| G4 Allineamento | **PASS** | 2/2; M4_s = 1.00, 1.00 |
| G5 Sandbox | **PASS** | 24/24 authorized + mondo |
| G6 Deny fuori | **PASS** | 24/24 ActionDenied |
| G7 Episodio | **PASS** | 24/24 `outcome_contract` + magnitude + T0&lt;T3 |
| G8 Anti-Maria | **PASS** | 21 template distinti, maria_like=2 |

Unico errore di routing: **G22** gold=billing pred=technical
(testo su stato UNKNOWN del ledger — dominio misto; non fa cadere G1).

Raw confidence resta alta (tipicamente ≥0.99): non nascosta.

---

## Cosa dimostra

Su ticket **eterogenei** (fatture, crash, sales, chargeback, webhook, SSO,
partnership, rimborsi EN/IT, kill stale/mismatch/conflict/hash/UNKNOWN/down):

1. il routing generalizza oltre il template Maria;
2. lo strutturale continua a rifiutare quando i fatti lo richiedono;
3. la divergenza testo/ledger vuoto e l’allineamento ledger pieno restano;
4. policy + contratto episodio tengono sul 100% della batteria.

## Cosa NON dimostra

- Copertura di tutto il dominio support reale (n=24, tre reparti).
- Che i fenomeni PCT effect_flip/catastrophe esistano nel traffico.
- Robustezza a rituning avversario del detector (K10 resta ferita nota fuori
  da questa batteria).
- Che accuracy routing 95% regga su migliaia di ticket — soglia era ≥75%.

---

## Relazione con la chiusura progetto

Questo passaggio era l’ultimo dichiarato aperto in `RAPPORTO_CHIUSURA.md`
(*«non dimostra generalizzazione»*). Ora la generalizzazione **operativa**
definita in pre-registrazione è misurata e **sostenuta**.

Il progetto può chiudersi senza nascondere i limiti sopra.
