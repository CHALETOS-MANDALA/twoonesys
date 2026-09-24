# CHANGELOG

## 0.3.1 — 2026-09-24

A decision that already happened can be handed to the harness.

- `occhio_ponte.consegna` writes the typed verdict (`choice`, `noul`, or `score`).
- Probability and confidence are dropped. They do not allow or deny.
- A sentence in the verdict is refused before the policy runs.
- The model is not in this package.

## 0.3.0 — 2026-09-22

Second world-touching policy. Still a harness, still inspectable.

- `exec.sandbox`: a process starts only as `[this interpreter, one .py already inside the sandbox]`. No shell, no `-c`, no other binary.
- The policy decides whether the process may start. It is not an OS jail after start.
- `fs.write.sandbox` unchanged.

## 0.2.1 — 2026-09-22

Clean-clone holes a reviewer found by running, not reading.

- Declare `cryptography`; extras `[dev]`, `[a2a]`, `[ml]`. `uvicorn` in `[a2a]`.
- FastAPI is optional at import time.
- `verify_receipt(rec)` uses the default public-key registry.
- Shipped fixture receipt (portable path, no private key).
- Torch tests `importorskip`; pytest path is `tests/`, not `cascade/tests`.
- PCT README: 100 tests.

## 0.2.0 — 2026-09-20

Prodotto minimo vendibile, sul disco.

- Oracolo: `run_verified` accetta solo `model_value` tipizzato (str/Decimal).
  Niente `float`, niente claim costruito dalle cifre del kernel.
- API: `from cascade import guarded` — policy `fs.write.sandbox`.
- CLI: `python -m cascade verify receipt.json`.
- Ricevuta `cascade.receipt.v1` firmata, verificabile con le sole chiavi pubbliche.
- Demo: `examples/blocked_agent.py` — agente bloccato, ricevuta sul disco.
- Licenza Apache-2.0. Packaging `cascade-soh`.
- Run LBP: `--fail-rate` deve essere 0; propensione 1.0 (un solo braccio).

Non ancora: curva AUC/ECE su n=120 con oracolo sul modello vivo.
Quella resta macchina, non codice.
