# CHANGELOG

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
