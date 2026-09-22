# Emendamento RUN8 — tolleranze §6 compilate (solo da protocollo pubblicato)

**Data:** 2026-09-21  
**Prima di:** qualunque costruzione OOD o eval del detector strutturale.  
**Fonte esclusiva:** ancoraggi in `PREREGISTRAZIONE_RUN8_DETECTOR.md` §6.1
(RUN2/5/6/7). Nessun numero nuovo.

Questo emendamento **chiude** la checklist §6 e rende RUN8 eseguibile
nel metodo. Non tocca H0/H1, tipi OOD, né il confronto appaiato.

---

## Tolleranze di preservazione laboratorio (in-distribution, seed 2026)

| Vincolo | Valore | Derivazione |
|---|---|---|
| ECE strutturale max | **≤ 0.10** | soglia primaria invariata del protocollo |
| AUC strutturale min | **≥ 0.70** | soglia primaria invariata del protocollo |
| ΔECE vs M4-testuale appaiato | **≤ 0.0287** | margine pubblicato 0.10 − 0.0713 (RUN7 M4) |
| ECE strutturale non oltre M4 + margine | implicitamente ⊆ ECE ≤ 0.10 | coerenza col margine |

Lettura: lo strutturale può essere al massimo “alla soglia storica”, e non
può allontanarsi da M4-testuale più di quanto M4 stesso stava sotto soglia.

## OOD — metrica primaria di miglioramento e test

| Voce | Scelta congelata | Perché (protocollo) |
|---|---|---|
| Metrica primaria OOD | **ECE** della confidence post-M4 | primaria di calibrazione in tutto RUN2–7 |
| Secondarie OOD (riportate, non decidono da sole) | Brier, NLL; false authorization se il sotto-banco ha asse policy | §4.2–4.3 RUN8 |
| Test | differenza appaiata `ECE_testuale − ECE_strutturale` su casi OOD; **IC95 bootstrap**, B=2000, seed=8 | cultura IC del protocollo; seed fissato ora |
| Miglioramento verificabile | IC95 della differenza **esclude 0** dal lato positivo (testuale peggiore) | analogo a «IC esclude 0.5» usato per AUC |
| n OOD | **96** casi (12 per ciascuno dei 8 tipi D1–D8) | multiplo uniforme dei 8 tipi; dichiarato prima; non Hanley (qui la primaria è ECE appaiata) |

## Metrica critica da non peggiorare (OOD)

| Voce | Valore |
|---|---|
| Critica | **ECE** (stessa primaria): lo strutturale non può avere ECE_OOD **maggiore** di ECE_OOD del testuale oltre la tolleranza zero — cioè il miglioramento è unidirezionale; se l’IC non esclude 0, H0 resta |
| Policy | se il sotto-banco OOD include azioni autorizzate: false-authorization rate strutturale **≤** testuale (appaiato, conteggio). Se un tipo D* non ha asse policy, si riporta N/A senza inventare |

## Detector — metriche e soglia confusion

| Voce | Scelta |
|---|---|
| Primarie detector | **AUROC e AUPRC** (threshold-free) |
| Confusion matrix | riportata a soglia **s = 0** sul soft-score (presente se s>0), come binarizzazione già usata in RUN6/7 — non una soglia nuova |
| Brier/NLL detector | secondarie |

## Criterio di successo — operativo (H1)

H1 è sostenuta (H0 rifiutata) sse:

1. In-distribution: ECE_strutt ≤ 0.10 ∧ AUC_strutt ≥ 0.70 ∧ (ECE_strutt − ECE_M4_testuale) ≤ 0.0287  
2. OOD: IC95 bootstrap di (ECE_testuale − ECE_strutturale) esclude 0 in favore dello strutturale  
3. OOD: ECE_strutt ≤ ECE_testuale (coerente con 2) e, dove definita, false-authorization_strutt ≤ false-authorization_testuale  

Altrimenti H0 non rifiutata. Rapporto pubblicato in ogni caso.

## Firma emendamento

```
data: 2026-09-21
chiude: PREREGISTRAZIONE_RUN8_DETECTOR.md §6
```
