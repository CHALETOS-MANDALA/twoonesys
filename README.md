# TWOONESYS

> A decision is not enough. TWOONESYS records why an action was allowed, proves what was decided, then records what actually happened.

A System One **harness**, not a model.

This repository is **only TWOONESYS**. SIX, LATENT_BRAIN+, PRISM, KIARNEL,
ENI, SIX-IDE and MORPH are not here and are not published. If you
want those, ask Rubinho Brazil directly.

## Why it exists

Not to compete with [JEV](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
(Diogo Almeida / TypeSafe). JEV is the System One decision: fast, typed,
no generated essay. The feeling it leaves is honest: *can I trust that
number enough to touch the world?*

TWOONESYS is a method to **improve that part** — the part after the
decision. Same class of harness (System One). CASCADE authorizes or
blocks on evidence and leaves a signed receipt. PCT writes the episode
**after** the outcome. Raw confidence stays visible. A high number does
not move the policy.

We do not claim to be JEV, to replace JEV, or to be 100% sure of the
verdict. We claim the verdict can be **inspected**:
logits → raw conf → receipt → world → episode.

**Author:** Rubinho Brazil (CASCADE, PCT, gate).  
**Not this repo:** JEV is Diogo Almeida / TypeSafe. Rizzo Flow (`engine/`) is Simone Rizzo / Rizzo AI Academy.

```
state
  → engine (optional, 0 tokens)     raw confidence, never hidden
  → CASCADE                         allow / deny + signed receipt
  → world
  → PCT episode                     T0 < T3, outcome after the fact
```

## What is in this repository

| Path | What | Whose |
|---|---|---|
| `harness/` | CASCADE | Rubinho Brazil |
| `pct/` | PCT | Rubinho Brazil |
| `bridge/` | gate `:8018`, episode contract, demos | Rubinho Brazil |
| `engine/` | Rizzo Flow, vendored | Simone Rizzo (Apache-2.0) |

## What is not in this repository

PRISM, KIARNEL, LATENT_BRAIN+, ENI, SIX-IDE, MORPH. CASCADE can call them through env paths. They are other organs. See [`docs/ORGANI_COLLEGATI.md`](docs/ORGANI_COLLEGATI.md).

## Quick check (no SIX, no cloud)

```text
cd harness
pip install -e ".[dev]"
python examples/blocked_agent.py
python -m cascade verify examples/receipts/blocked_receipt.json
python -m pytest tests -q
```

An agent tries to write outside the sandbox. CASCADE denies. The receipt is the proof.
The receipt is **written by the example**, not shipped (live receipts stay gitignored).
Verify uses the public keys in `harness/run/public_keys.json` from that same run.
A committed copy lives at `harness/examples/fixtures/` so a clone can verify without executing:

```text
python -m cascade verify examples/fixtures/blocked_receipt.json --registry examples/fixtures/public_keys.json
```

`pytest` without torch: those tests skip. Full suite: `pip install -e ".[dev,ml]"`.

With the engine up (`bridge/AVVIA_ENGINE.bat` then `bridge/AVVIA_GATE.bat` — 4B weights are **not** in this repo):

```text
python bridge/e2e_chiudi.py
```

## Limits (read these before citing)

- Lab generalization: n=24 tickets, gates G1–G8 in `bridge/RAPPORTO_GENERALIZZAZIONE.md`. Not all of support traffic.
- Kill suite: 9/10 holds. Wound **K10** (value attached without verdict) is left visible, not tuned away.
- PCT: episodic information wins in **2 of 4** originally predicted regimes, on a simulated world. Real-world effect_flip / catastrophe are often still not observable.
- Raw confidence can sit at 0.999 and still be wrong for the world. That is why the receipt and the episode exist.
- Gate **soft** (SIX default): if `:8018` is down, local control-plane may proceed. Strict = deny.

## License

Apache-2.0 (`LICENSE`). `NOTICE` is attribution (Simone Rizzo, Diogo Almeida), not a second license.
