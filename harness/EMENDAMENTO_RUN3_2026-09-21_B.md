# Emendamento 2026-09-21/B (RUN3) a PREREGISTRAZIONE_RUN2_TWOONESYS.md

Terza modifica datata. Congelato (c16f872), emendamento anchor e emendamento
RUN3 restano intoccati. Nessuna analisi è stata fatta sui dati parziali:
queste modifiche precedono qualunque lettura dei risultati.

## 1. Floor VRAM: 1024 → 512 MiB, solo per RUN3

**Scoperta:** la banda stazionaria del 4B residente oscilla 700-1260 MiB
(misurata su 138 tentativi): il floor a 1024 nullificava metà dei record per
rumore del modello stesso, non per contenzione (Ollama verificato scarico).
La contenzione vera (un ricarico Ollama da 4,6 GB) porta i liberi a ~0, e se
l'engine andasse in OOM il record nullificherebbe comunque per errore engine
(regola §7.1). Floor **512 MiB**: la funzione anti-contenzione è preservata,
il rumore stazionario no.

## 2. Bug del banco: arresto anticipato (dichiarato)

Il ciclo si è fermato a 71 valide / 30 fallimenti per una condizione di break
scritta male (`attempts >= 120` invece di `valid >= 120`). La regola congelata
(§6: si continua finché **entrambe** le condizioni — 120 valide E 30
fallimenti) resta quella vigente; il bug le disobbediva. Il banco è corretto
e il run **riprende** dai record già raccolti (`--resume`): i 71 record validi
sono stati raccolti sotto un floor *più stretto* di quello vigente, quindi
conservarli è conservativo. I nulli si conservano col loro motivo, come sempre.

## 3. Invariato

Ipotesi, oracolo, fasce, soglie, baseline, criteri di falsificazione,
pubblicazione garantita.
