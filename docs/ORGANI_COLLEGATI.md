# Organi collegati — non copiati in questa repo

CASCADE può usarli. TWOONESYS non li contiene.

| Organo | Ruolo accanto a CASCADE | Come si collega | In repo? |
|---|---|---|---|
| **PRISM** | pertinenza dei documenti (`prism.relevance`) | `CASCADE_PRISM_PATH` | no |
| **KIARNEL** | oracolo numerico; giudica il claim, non lo inventa | `CASCADE_MATEMATICA_KERNEL` | no |
| **LATENT_BRAIN+** | memoria / decode di SIX | `latent_bridge.py` se il cervello è su `:8000` | no |
| **ENI** | proponente opzionale | `eni_brain.py` | no |
| **Rizzo Flow** | engine System One locale, 0 token | `engine/` vendored + `:8017` | sì, codice; no i pesi |
| **JEV** | harness/modello System One di Diogo Almeida | nessuno: non è questo progetto | no |

Senza PRISM, KIARNEL o LBP, CASCADE continua a fare il suo mestiere: **bloccare, firmare, registrare**. I test che richiedono quei backend sono `skip` se il path manca.

Questa repo pubblica è **solo TWOONESYS**. SIX e gli altri organi non si
toccano e non si pubblicano, almeno per ora. Chi vuole di più chiede a
Rubinho Brazil, non cerca un monorepo.
