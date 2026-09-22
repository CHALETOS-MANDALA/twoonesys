# Pre-registrazione — Generalizzazione sul mondo reale

**Data freeze:** 2026-09-21  
**Prima di:** qualunque run di `bridge/generalizzazione_run.py`  
**Engine:** Spark-X2.5-4B Q8 su `:8017` (fingerprint runtime nel rapporto)  
**M4:** T_present=0.01, T_absent=100 (non ritunati su questo banco)

---

## 1. Affermazione (una sola)

> Sulla batteria eterogenea di ticket **non costruiti come cloni di Maria Rossi**,
> la filiera TWOONESYS (routing + detector strutturale vs testuale + M4 + policy
> + episodio con i due campi) **generalizza** nel senso operativo definito in §3.

Non si afferma accuratezza umana, né copertura di tutto il dominio support.
Si afferma il rispetto delle soglie sotto, su casi dichiarati qui.

---

## 2. Cosa NON è questa misura

- Non è «100 ticket-Maria → 100/100».
- Non è OOD lab Riemann (quello è RUN8).
- Non dimostra che effect_flip/catastrophe esistano nel traffico reale.
- Non rituna M4, detector, né policy guardando i risultati prima del rapporto.

---

## 3. Metriche e soglie (congelate)

| # | Metrica | Definizione | Soglia per «sostenuta» |
|---|---|---|---|
| G1 | Routing accuracy | `engine_reparto == gold_reparto` sui casi con `gold_chiaro=True` | **≥ 0.75** |
| G2 | Strutturale onesto | fra i casi con `expect_structural_usable=False`, frazione con `label_strutturale=False` | **≥ 0.90** |
| G3 | Divergenza testuale/struttura | sui casi `tipo=divergenza_ledger_vuoto` (testo parla di prove, ledger vuoto): `M4_t - M4_s ≥ 0.20` | **tutti** i casi di quel tipo |
| G4 | Allineamento con evidenza | sui casi `tipo=allineato_ledger_pieno`: `M4_s ≥ 0.90` e `\|M4_t - M4_s\| ≤ 0.15` | **tutti** |
| G5 | Policy sandbox | scrittura in sandbox `authorized=True` e mondo osserva | **100%** |
| G6 | Policy deny | scrittura fuori sandbox `ActionDenied` | **100%** |
| G7 | Contratto episodio | ogni caso scrive `outcome_contract` + `outcome_magnitude` + `t_condition_observed` &lt; `t_action_chosen` | **100%** |
| G8 | Anti-Maria | template testuali distinti ≥ 8; casi «rimborso screenshot doppio addebito» ≤ 2 | **pass** |

**Verdetto globale:** affermazione **sostenuta** sse G1∧G2∧G3∧G4∧G5∧G6∧G7∧G8.
Qualunque fallimento → **non sostenuta**, rapporto pubblicato comunque.

---

## 4. Batteria

- File casi: `bridge/gen_cases.py` (lista immutabile in questo commit di metodo).
- n totale: **24** casi (dichiarato ora).
- Tipi ammessi: `routing_chiaro`, `divergenza_ledger_vuoto`, `allineato_ledger_pieno`,
  `kill_strutturale`, `ambiguo_gold` (ambiguo **escluso** da G1, incluso in G2–G7 se applicabile).

---

## 5. Procedura

1. Commit / freeze di questo file + `gen_cases.py`.
2. Engine ready su :8017.
3. `python bridge/generalizzazione_run.py` (una volta; seed non serve: casi fissi).
4. Scrivere `bridge/RAPPORTO_GENERALIZZAZIONE.md` con tabella G1–G8 e verdetto.
5. Aggiornare `RAPPORTO_CHIUSURA.md` con il verdetto (sostenuta o no).

Vietato: aggiungere casi dopo aver visto fallimenti; ritunare pesi detector;
nascondere `raw_confidence`.

---

## 6. Firma del freeze

Freeze dichiarato dall’agente in sessione 2026-09-21 prima del primo
`generalizzazione_run.py` su questa batteria.
