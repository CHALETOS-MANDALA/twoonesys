# Prova TWOONESYS tu stesso

## Due finestre

1. **Engine** (lasciala aperta)  
   Doppio click: `bridge\AVVIA_ENGINE.bat`  
   Aspetta `ready` su :8017.  
   Se la GPU è piena: `ollama stop <modello>` prima.

2. **Prova**  
   Doppio click: `bridge\AVVIA_PROVA.bat`  
   (oppure `python bridge\prova_tu.py` dalla cartella TWOONESYS)

## Cosa fai tu

1. Incolla un **ticket reale** (o un messaggio vero).
2. Ti chiede: *il ledger di sistema ha evidenza verificata?*  
   - **s** = fatto strutturale presente  
   - **n** = ledger vuoto (anche se il testo parla di screenshot)
3. Vedi:
   - decisione dell’engine
   - confidenza grezza
   - M4 con detector **testuale** vs **strutturale**
   - se divergono, te lo segnala
4. Scrive in sandbox → ricevi ricevuta firmata.
5. Opzionale: prova scrittura *fuori* sandbox → deve essere bloccata.

## Cosa guardare

Prova lo **stesso testo due volte**: una con ledger **s**, una con **n**.  
Se il testo parla di prove ma il ledger è vuoto, il testuale resta alto e lo strutturale scende — è la tesi.

Sessioni in: `bridge\run_prova\session.jsonl`  
File: `bridge\sandbox_prova\`  
Ricevute: `bridge\receipts_prova\`
