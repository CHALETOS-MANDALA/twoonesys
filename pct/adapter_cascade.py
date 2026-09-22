"""Adattatore dal log reale di CASCADE al formato che `detector.py` si aspetta.

Il punto di questo file NON e' far girare il rilevatore a ogni costo: e'
dichiarare, campo per campo, cosa c'e' davvero nel log e cosa e' stato
SOSTITUITO -- perche' una sostituzione taciuta produce una diagnosi che sembra
una misura e non lo e'.

    python3 adapter_cascade.py <log.jsonl> [--stato action|action+escalated]

Corrispondenze e sostituzioni, tutte esplicite:

  state_key           NON esiste nel log. Si costruisce da campi gia' presenti
                      (`action`, opzionalmente `escalated`). E' una scelta
                      dell'adattatore, non un dato: va dichiarata nel rapporto.
  action              `action_chosen` se presente, altrimenti `action`.
  selection_prob      `selection_probability`. Se manca o e' nulla, il
                      confondimento NON e' diagnosticabile: non si stima, si dice.
  outcome_magnitude   NON esiste. SOSTITUITA con +1 / -1 da `outcome`. Conseguenza
                      dichiarata: senza magnitudini vere la coda pesante non puo'
                      esistere per costruzione, quindi il fenomeno CATASTROPHE
                      risultera' sempre assente. E' un limite del log, non del
                      dominio.
  t                   `touched` (timestamp), altrimenti l'ordine di riga.
  condizione          `escalated` e' l'unico candidato presente. ATTENZIONE: e'
                      pre-decisione solo se viene deciso PRIMA dell'azione. Se
                      e' una conseguenza della decisione, e' un collider e non
                      va usato -- l'adattatore lo segnala e lascia decidere a chi
                      conosce il codice che lo scrive.
"""

from __future__ import annotations

import argparse
import sys

from detector import carica, diagnostica

CAMPI_ATTESI = ("state_key", "action", "selection_probability",
                "outcome_magnitude", "t")


def converti(righe: list[dict], stato: str = "action") -> tuple[list[dict], list[str]]:
    """Restituisce (record convertiti, elenco delle sostituzioni applicate)."""
    note: list[str] = []
    if not righe:
        return [], ["log vuoto"]

    presenti = set(righe[0].keys())
    chiavi_stato = sorted(set())

    # --- state_key
    if stato == "action+escalated":
        componenti = ("action", "escalated")
    else:
        componenti = ("action",)
    mancanti = [c for c in componenti if c not in presenti]
    if mancanti:
        raise SystemExit(f"campi assenti per costruire lo stato: {mancanti}")
    note.append(f"state_key COSTRUITA da {componenti} (non esiste nel log)")

    # --- azione
    campo_azione = "action_chosen" if "action_chosen" in presenti else "action"
    if campo_azione == "action":
        note.append("action_chosen assente: si usa `action`, che nel log e' il TIPO "
                    "di azione, non il braccio scelto")

    # --- propensione
    ha_prop = "selection_probability" in presenti

    # --- magnitudine
    note.append("outcome_magnitude ASSENTE: sostituita con +1/-1 da `outcome`. "
                "Conseguenza: CATASTROPHE non puo' risultare presente")

    stati: dict[tuple, int] = {}
    azioni: dict[object, int] = {}
    out = []
    for i, r in enumerate(righe):
        chiave = tuple(r.get(c) for c in componenti)
        s = stati.setdefault(chiave, len(stati))
        a_raw = r.get(campo_azione)
        a = azioni.setdefault(a_raw, len(azioni))
        esito = r.get("outcome")
        mag = 0.0 if esito is None else (1.0 if esito else -1.0)
        p = r.get("selection_probability") if ha_prop else None
        out.append({
            "state_key": s,
            "action": a,
            "selection_probability": float(p) if p else 0.0,
            "outcome_magnitude": mag,
            "t": r.get("touched", i),
            "escalated": int(bool(r.get("escalated", False))),
        })

    note.append(f"stati distinti: {len(stati)}   azioni distinte: {len(azioni)}")
    if len(azioni) < 2:
        note.append("UNA SOLA AZIONE nel log: nessun confronto fra bracci e' "
                    "possibile, ne' qui ne' altrove")
    if not ha_prop or all(r["selection_probability"] <= 0 for r in out):
        note.append("PROPENSIONE assente o nulla: il confondimento non e' "
                    "diagnosticabile e non lo sara' mai per questi record")
    return out, note


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--stato", default="action",
                    choices=["action", "action+escalated"])
    ap.add_argument("--condizione", default=None,
                    help="campo da usare come condizione (es. escalated). "
                         "Usalo solo se e' osservabile PRIMA della decisione.")
    args = ap.parse_args(argv)

    righe = carica(args.log)
    conv, note = converti(righe, args.stato)

    print(f"\nlog: {args.log}   record: {len(righe)}")
    print("\nsostituzioni e limiti dichiarati:")
    for n in note:
        print(f"  - {n}")

    if args.condizione == "escalated":
        print("  - ATTENZIONE: `escalated` e' usato come condizione. E' lecito "
              "SOLO se\n    viene deciso prima dell'azione. Se e' una conseguenza "
              "della decisione,\n    e' un collider e la diagnosi che segue e' "
              "fabbricata.")

    print(f"\n{'fenomeno':<24} {'stato':>16} {'misura':>10}  nota")
    print("-" * 90)
    # le magnitudini sono sostituite con +-1: la coda pesante non e' osservabile
    for d in diagnostica(conv, args.condizione, magnitudini_vere=False):
        print(f"{d.fenomeno:<24} {d.stato.value:>16} {d.misura:10.4f}  {d.nota}")

    print("\nCome si legge:")
    print("  rilevato        il fenomeno c'e' in questo log")
    print("  assente         misurato, e non c'e'")
    print("  non osservabile il log non ha i campi per accorgersene -- NON e' "
          "un'assenza")
    print("\nQuesti numeri non dicono se PCT serve: dicono quanto fenomeno "
          "c'e' qui.\nIl valore per unita' di fenomeno viene da §9.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
