"""Demo di vendita: un agente prova a scrivere fuori sandbox e viene bloccato.

La ricevuta dimostra il rifiuto. Verifica:

    python -m cascade verify examples/receipts/blocked_receipt.json
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from cascade import ActionDenied, guarded

HERE = Path(__file__).resolve().parent
SANDBOX = HERE / "sandbox"
RECEIPTS = HERE / "receipts"


def main() -> int:
    SANDBOX.mkdir(exist_ok=True)
    RECEIPTS.mkdir(exist_ok=True)
    os.environ["CASCADE_SANDBOX"] = str(SANDBOX)

    @guarded(receipt_dir=RECEIPTS)
    def scrivi_report(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    vietato = HERE / "non_doveva_esistere.txt"
    try:
        scrivi_report(vietato, "payload che non deve toccare il disco")
    except ActionDenied as denied:
        out = RECEIPTS / "blocked_receipt.json"
        denied.receipt.save(out)
        print("BLOCCATO")
        print(denied.receipt.to_json())
        print(f"RICEVUTA={out}")
        print("Verifica: python -m cascade verify", out)
        return 0
    print("ERRORE: l'agente non e' stato bloccato")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
