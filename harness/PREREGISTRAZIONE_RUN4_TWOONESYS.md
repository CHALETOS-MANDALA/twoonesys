# Pre-registrazione — Run 4: la calibrazione chiude la catena?

**Stato: CONGELATA dal commit che introduce questo file.** Modifiche solo in
documenti successivi, datati.

| | |
|---|---|
| Autore | Rubinho (metodo ereditato: RUN1 → RUN2 → RUN3) |
| Data | 2026-09-21 |
| Proponente | TWOONESYS engine, Spark-X2.5-4B Q8, :8017, **con temperatura fittata** |
| Digest del contratto misurato | `twoonesys-run2-v1` (invariato) |

---

## 1. L'unica affermazione da misurare

> Con la temperatura fittata come in §2, la confidenza dell'engine predice il
> successo con AUC ≥ 0.70 **ed è calibrata** con ECE ≤ 0.10 su 10 bin,
> **fuori campione** (casi mai visti dal fit).

È la stessa frase di RUN2/RUN3. RUN2 e RUN3 hanno mostrato che la metà
«discriminazione» regge e la metà «calibrazione» cade. RUN4 chiede se la
ricalibrazione — il componente che quei run hanno giustificato — chiude la
catena.

## 2. Fit e valutazione: la separazione dichiarata

- **Fit set**: i 120 casi del banco con seed 42 (stessa popolazione di RUN3),
  ri-interrogati sull'engine **non calibrato** per catturare `option_logits`
  crudi. Righe `LabeledLogits` (type=numeric, logits in ordine dei candidati,
  `label_index` = posizione dell'anchor vero — la verità dal kernel, mai
  hardcoded). Fit con `rizzo calibrate` (ricerca di griglia NLL dell'engine,
  fingerprint vincolato ai pesi). I logit sono deterministici dati i pesi:
  la raccolta non è soggetta al floor VRAM (la pressione produce errori, non
  logit diversi); gli errori engine in raccolta si ritentano (max 3) o il
  caso si scarta e si dichiara.
- **Eval set**: RUN4 = run fresco con **seed 2026** — stati e distrattori
  mai visti dal fit. Server riavviato con `--calibration`. Stesse fasce,
  stesse soglie, stessa regola di arresto (120 valide / ≥30 fallimenti,
  tetto 200), stesse esclusioni (floor 512 MiB per il 4B, emendamento
  2026-09-21/B), stesse baseline B0/B1/B2.

Nessuna sovrapposizione di istanze fra fit e valutazione. Il fit vede seed 42,
la valutazione vede seed 2026: dichiarato qui, prima di tutto.

## 3. Predizione dichiarata in anticipo

La temperatura è monotona: **l'ordinamento non cambia → AUC atteso ~invariato**
(rispetto a RUN3: 0.775 [0.693, 0.857]). L'ECE deve scendere se il fit
generalizza. Se l'ECE non scende fuori campione, la calibrazione non
generalizza e **si pubblica questo**, non una versione edulcorata.

## 4. Cosa falsifica l'affermazione

- IC95 dell'AUC contiene 0.5, oppure AUC crolla rispetto a RUN3 senza
  spiegazione → il fit ha rotto il segnale.
- AUC ≥ 0.70 ma ECE > 0.10 → la calibrazione non generalizza fuori campione.
- Nessuna differenza fra le fasce → il banco, non il sistema.

**Il rapporto si pubblica in tutti i casi.**

## 5. Invariato da RUN2/RUN3

Oracolo (kernel zeron, claim = ancora scelta), fasce A/B/C, propensione 1.0
dichiarata (nessuna stima off-policy), `label_source="mechanical"`, pilota da
20 con soli controlli meccanici prima del run, regola di arresto su `n`,
pubblicazione garantita.

## 6. Firma

```
data: 2026-09-21
commit: (il commit che introduce questo file congela il metodo)
```
