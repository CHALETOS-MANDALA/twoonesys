"""CLI: cascade verify receipt.json"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .guarded import default_key_registry
from .receipt import ActionReceipt, verify_receipt
from .signing import KeyRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cascade",
        description="CASCADE — harness System One. Verifica una ricevuta firmata.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="verifica una ricevuta con le chiavi pubbliche")
    verify.add_argument("receipt", type=Path)
    verify.add_argument(
        "--registry", type=Path, default=None,
        help="JSON delle chiavi pubbliche (default: run/public_keys.json)")
    args = parser.parse_args(argv)

    if args.cmd == "verify":
        if not args.receipt.is_file():
            print(f"file mancante: {args.receipt}", file=sys.stderr)
            return 2
        rec = ActionReceipt.load(args.receipt)
        keys = default_key_registry() if args.registry is None else KeyRegistry(args.registry)
        ok, message = verify_receipt(rec, keys)
        print(message)
        print(
            f"chi={rec.principal} cosa={rec.tool}:{rec.scope} "
            f"quando={rec.created_at} evidenza={rec.evidence_ref or '-'} "
            f"autorizzata={rec.authorized} esito={rec.outcome}"
        )
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
