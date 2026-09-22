# CASCADE — System One Harness

Un runtime che sta fra l'agente e il mondo. Riceve una proposta, la passa
da evidenza e policy, **autorizza o blocca**, osserva l'esito, lascia una
ricevuta firmata.

Non e' un modello. Non e' Jev. Non e' osservabilita'.

> Dopo un incidente: la prova che l'azione non poteva partire senza un
> permesso legato a un'evidenza.

## Installazione

Questa cartella è il pacchetto CASCADE, dentro la repo TWOONESYS:

```text
cd harness
pip install -e ".[dev]"
python examples/blocked_agent.py
python -m cascade verify examples/receipts/blocked_receipt.json
```

The receipt is written by the example. On a fresh clone, verify the fixture:

```text
python -m cascade verify examples/fixtures/blocked_receipt.json --registry examples/fixtures/public_keys.json
```

## Uso

```python
from cascade import guarded, ActionDenied

@guarded(policy="fs.write.sandbox")
def scrivi_report(path, contenuto):
    Path(path).write_text(contenuto, encoding="utf-8")

# esegue e restituisce la ricevuta, oppure solleva ActionDenied
```

Una sola policy in v1: `fs.write.sandbox`. Path fuori dal sandbox
(`CASCADE_SANDBOX`) = blocco + ricevuta.

## Verifica di una ricevuta

```text
python -m cascade verify receipt.json
```

Usa solo le chiavi pubbliche. Chiave sconosciuta = non verificabile.

## Demo (agente bloccato)

```text
python examples/blocked_agent.py
python -m cascade verify examples/receipts/blocked_receipt.json
```

Or the shipped fixture: `examples/fixtures/blocked_receipt.json`.

## Cosa e' vero oggi

- Cancelllo Z3 a tre passi: solo `RULES_VERIFIED` autorizza.
- Claim numerico: nasce dal **modello** (`CLAIM_VALUE=` o `model_value=`),
  giudicato dal kernel. Mai `float`, mai auto-verifica.
- Esito osservato, distinto da `approved`.
- Ricevuta `cascade.receipt.v1` firmata, verificabile dopo riavvio.

## Cosa non e' ancora una misura

La curva AUC/ECE su n=120 con ≥30 fallimenti e oracolo sul modello vivo
non e' pubblicata. Il codice del banco c'e'; manca il tempo di macchina.
Non si dice «calibrato».

## Conformita'

```text
python -m pytest tests -q
python -m pytest tests/test_soh_conformance.py -q
```

Licenza: Apache-2.0. Modello di minaccia: `THREAT_MODEL.md`.
Pre-registrazione del run di misura: `PREREGISTRAZIONE_RUN1.md`.
