"""Scala e predizione falsificabile (spec §10.4).

    Con dati stazionari e abbondanti l'aggregato e' SUFFICIENTE.

Quindi il vantaggio di B deve RESTRINGERSI al crescere di n nei regimi
stazionari, e PERSISTERE solo dove c'e' non-stazionarieta' o eventi rari.
Se svanisce anche li', PCT e' un correttivo per piccoli campioni e non
un'architettura: si chiude.

Uso:  python3 scaling.py [--seed S] [--sizes 30000,120000,480000]
"""

from __future__ import annotations

import argparse
import sys

from runner import run_phenomenon

STAZIONARI = ("nessuno", "confound")
NON_STAZIONARI = ("effect_flip", "catastrophe")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sizes", type=str, default="30000,120000,480000")
    args = ap.parse_args(argv)
    taglie = [int(x) for x in args.sizes.split(",")]

    print("\nPCT -- scala (spec §10.4)")
    print("vantaggio = (rimpianto A - rimpianto B) / rimpianto A\n")
    intestazione = f"{'fenomeno':<14}" + "".join(f"{n:>12}" for n in taglie) + "   atteso"
    print(intestazione)
    print("-" * len(intestazione))

    andamenti: dict[str, list[float]] = {}
    for f in STAZIONARI + NON_STAZIONARI:
        riga, vant = f"{f:<14}", []
        for n in taglie:
            c = run_phenomenon(None if f == "nessuno" else f, seed=args.seed,
                               n_episodes=n)
            a = c.arms["A_aggregato"].regret_mean
            b = c.arms["B_pct"].regret_mean
            v = (a - b) / a if a > 0 else 0.0
            vant.append(v)
            riga += f"{v:11.1%} "
        andamenti[f] = vant
        riga += "  si restringe" if f in STAZIONARI else "  deve persistere"
        print(riga)

    print("\ncosti al variare della scala (primo fenomeno):")
    for n in taglie:
        c = run_phenomenon(None, seed=args.seed, n_episodes=n)
        b = c.arms["B_pct"]
        a = c.arms["A_aggregato"]
        print(f"  n={n:>7}  indice B {b.bytes_retained/1024:9.1f} KiB "
              f"({b.bytes_retained/max(a.bytes_retained,1):6.0f}x A)  "
              f"query {b.query_seconds*1000:8.1f} ms")

    print("\nverdetto sulla predizione:")
    for f in NON_STAZIONARI:
        v = andamenti[f]
        persiste = v[-1] > 0.5 * v[0] and v[-1] > 0.05
        print(f"  {f:<14} {'persiste' if persiste else 'SVANISCE -> chiudere'}"
              f"  ({v[0]:.1%} -> {v[-1]:.1%})")
    for f in STAZIONARI:
        v = andamenti[f]
        print(f"  {f:<14} {'nessun vantaggio, come atteso' if abs(v[-1]) < 0.05 else 'INATTESO: vantaggio stazionario'}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
