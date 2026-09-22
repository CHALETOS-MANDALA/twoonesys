# Modello di minaccia — CASCADE v1 (una pagina)

**Asset:** il diritto di eseguire un'azione; la ricevuta che lo dimostra.

**Attaccante:** un agente (modello o orchestratore) che vuole scrivere fuori
dal sandbox, o un terzo che vuole far passare una ricevuta falsa.

**Cosa puo' fare l'attaccante**

1. Chiamare la funzione wrappata con un path fuori sandbox.
2. Presentare un grant copiato o gia' consumato.
3. Alterare una ricevuta dopo l'emissione.
4. Chiedere verifica con una chiave che non e' nello storico.

**Risposta**

1. Path risolto e confrontato con `CASCADE_SANDBOX`. Fuori = `ActionDenied` + ricevuta.
2. `GrantRegistry.authorize` e' l'autorita', non il documento. Monouso. Deep-compare dei params.
3. Firma Ed25519 sul payload canonico senza il campo `signature`.
4. Chiave sconosciuta = non verificabile. Mai un default positivo.

**Chi firma:** l'identita' in `run/signing_key.json` (privata, gitignored).
**Chi verifica:** `run/public_keys.json` o `--registry`. Solo pubbliche.
**Se la privata e' compromessa:** si ruota, si registra la nuova pubblica, le
ricevute vecchie restano verificabili con lo storico. La compromessa si
revoca smettendo di usarla; le ricevute gia' emesse non si riscrivono.
**Cosa questa v1 non copre:** registro grant persistente al riavvio,
multi-tenant, HTTP, un secondo dominio d'azione.
