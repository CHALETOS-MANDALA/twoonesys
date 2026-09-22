"""Adattatore episodi TWOONESYS → detector PCT.

Dichiarato campo per campo: cosa c'e' e cosa manca.
Con i due campi (ScalaCosti + tempi) CATASTROPHE e ordine diventano osservabili.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREC = ROOT / "pct"
sys.path.insert(0, str(PREC))

from detector import Diagnosi, Stato, diagnostica  # noqa: E402


def carica_episodi(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def converti(episodi: list[dict]) -> tuple[list[dict], list[str]]:
    note: list[str] = []
    if not episodi:
        return [], ["log episodi vuoto"]

    # Verifica contratto
    with_contract = sum(1 for e in episodi if e.get("outcome_contract"))
    with_mag = sum(1 for e in episodi if "outcome_magnitude" in e)
    with_t0 = sum(1 for e in episodi if e.get("t_condition_observed") is not None)
    with_t3 = sum(1 for e in episodi if e.get("t_action_chosen") is not None)
    note.append(f"outcome_contract presente: {with_contract}/{len(episodi)}")
    note.append(f"outcome_magnitude presente: {with_mag}/{len(episodi)}")
    note.append(f"t_condition→t_action: {with_t0}/{len(episodi)} → {with_t3}/{len(episodi)}")

    if with_mag == len(episodi):
        note.append("CATASTROPHE OBSERVABILE (scala dichiarata) — non era cosi' sul log CASCADE vecchio")
    else:
        note.append("CATASTROPHE ancora parzialmente non osservabile")

    stati: dict[tuple, int] = {}
    azioni: dict[object, int] = {}
    out = []
    for i, e in enumerate(episodi):
        chiave = (
            e.get("ledger_evidenza"),
            e.get("ref_ordine"),
        )
        s = stati.setdefault(chiave, len(stati))
        a_raw = e.get("reparto_scelto") or e.get("reparto") or "unknown"
        a = azioni.setdefault(a_raw, len(azioni))
        mag = float(e.get("outcome_magnitude", 0.0))
        # propensione: se manca, dichiarata — confound non diagnosticabile
        p = e.get("selection_probability")
        out.append({
            "state_key": s,
            "action": a,
            "selection_probability": float(p) if p else 0.0,
            "outcome_magnitude": mag,
            "t": e.get("t_action_chosen", i),
            "ledger_evidenza": int(bool(e.get("ledger_evidenza"))),
        })

    note.append(f"stati distinti={len(stati)}  azioni distinte={len(azioni)}")
    if not any(r["selection_probability"] > 0 for r in out):
        note.append("PROPENSIONE assente: CONFOUND non diagnosticabile (dichiarato)")
    return out, note


def diagnostica_episodi(path: Path) -> tuple[list[Diagnosi], list[str]]:
    episodi = carica_episodi(path)
    conv, note = converti(episodi)
    if not conv:
        return [], note
    # ledger_evidenza e' pre-decisione (FASI_CAMPI) → usabile come condizione
    diag = diagnostica(conv, "ledger_evidenza", magnitudini_vere=True)
    return diag, note


def stampa(path: Path) -> int:
    print(f"\n--- PCT su episodi: {path} ---")
    diag, note = diagnostica_episodi(path)
    print("sostituzioni / limiti:")
    for n in note:
        print(f"  - {n}")
    if not diag:
        print("  (nessuna diagnosi)")
        return 0
    print(f"\n{'fenomeno':<24} {'stato':>16} {'misura':>10}")
    print("-" * 56)
    for d in diag:
        print(f"{d.fenomeno:<24} {d.stato.value:>16} {d.misura:10.4f}")
    # Consiglio stato futuro
    rilevati = [d for d in diag if d.stato is Stato.RILEVATO]
    if any(d.fenomeno in ("effect_flip", "catastrophe") and d.presente for d in rilevati):
        consiglio = "CONSERVA EPISODI (fenomeno dove aggregato e' cieco)"
    elif any(d.stato is Stato.NON_OSSERVABILE for d in diag):
        consiglio = "CAMPI ANCORA INSUFFICIENTI — non concludere assenza"
    else:
        consiglio = "aggregato sufficiente per ora (nessun regime B rilevato)"
    print(f"\n  → stato futuro: {consiglio}")
    return 0


if __name__ == "__main__":
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "bridge" / "run_e2e" / "episodes.jsonl")
    raise SystemExit(stampa(log))
