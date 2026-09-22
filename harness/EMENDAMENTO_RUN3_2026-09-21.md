# Emendamento 2026-09-21 (RUN3) a PREREGISTRAZIONE_RUN2_TWOONESYS.md

Seconda modifica datata, come la regola impone. Il documento congelato
(c16f872) e il primo emendamento restano intoccati.

## 1. RUN3 = dataset separato (regola §7, nessuna novità)

Il `model_id` cambia: Spark-X2.5-**4B** Q8 (revisione pinnata
`0bcb3567...`), stesso contratto `twoonesys-run2-v1`, stesso banco, stesse
soglie (120 valide / ≥30 fallimenti / tetto 200), stesse baseline. I dati di
RUN2 (1.7B) **non si mescolano**: i due dataset si riportano affiancati.

## 2. Floor VRAM: 2048 → 1024 MiB, solo per RUN3

**Scoperta:** col 4B Q8 residente, lo stato stazionario è ~1,25 GiB liberi
(modello caricato per intero, health `ready`, nessuna pressione). Il floor di
2 GiB — scritto quando il piano assumeva l'1.7B (stazionario ~4 GiB liberi) —
marca nullo il 100% dei record senza rilevare contenzione reale.

**Funzione preservata:** il floor esiste per escludere decisioni prese sotto
pressione di memoria (es. ricarico di Ollama, che porterebbe i liberi a ~0).
Un floor di **1024 MiB** mantiene esattamente quella funzione per lo stato
stazionario del 4B: qualunque contenzione vera scende sotto 1 GiB e nulla il
record. Dichiarato qui, prima del pilota.

## 3. Invariato

Ipotesi, oracolo, fasce, regola di arresto su `n`, regole di esclusione
restanti, criteri di falsificazione, pubblicazione garantita: tutto come nel
documento congelato e nel primo emendamento.
