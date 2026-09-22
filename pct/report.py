"""Tabella dei risultati per fenomeno (spec §4.3, §9.2).

Uso:  python3 report.py [--episodes N] [--seed S] [--phenomena a,b,c]
"""

from __future__ import annotations

import argparse
import sys

from runner import Comparison, run_phenomenon

FENOMENI = ("nessuno", "confound", "effect_flip", "env_change", "catastrophe",
            "drift", "sparse", "low_support", "delay")

# Predizioni dichiarate PRIMA di girare (spec §10.4 e evidence_prec.py):
#   B deve vincere dove esiste una CONDIZIONE OSSERVABILE che l'aggregato ha
#   sommato via, o un evento raro. NON deve vincere su drift: quel regime cambia
#   senza marcatore osservabile, e vederlo richiederebbe una pesatura per
#   recency, che la carta vieta.
#: Predizioni riviste DOPO l'audit del banco e PRIMA del run definitivo:
#:  - confound esce dagli attesi: contro un aggregato FORTE (Hajek) la
#:    propensione basta gia' ad A, e nel mondo qui costruito d non cambia
#:    l'effetto relativo. Misurato, non ipotizzato.
#:  - env_change esce: il fold di struttura e' interamente prima del cambio,
#:    quindi non puo' scoprire che `e` conta. E' un limite del protocollo a fold
#:    congelati, non dell'idea -- e va riportato come tale.
ATTESO_VINCE_B = {"effect_flip", "catastrophe"}
ATTESO_PARI = {"nessuno", "confound", "env_change", "drift", "sparse",
               "low_support", "delay"}


#: valore dichiarato di un'unita' di rimpianto, e budget del costo di ritenzione.
#: Servono a trasformare "vantaggio %" in un PAREGGIO (spec §10.1): una soglia
#: arbitraria come "deve essere >=30%" non e' un criterio, e' un numero scelto.
VALORE_UNITA_RIMPIANTO: float = 1.0      # unita' di utilita' per punto di rimpianto
COSTO_PER_MIB: float = 0.50              # utilita' spesa per MiB conservato
COSTO_PER_MS: float = 0.002              # utilita' spesa per ms di latenza aggiunta


def pareggio(c: Comparison) -> tuple[float, float, bool]:
    """Beneficio e costo di B rispetto ad A, nelle stesse unita'."""
    b, a = c.arms["B_pct"], c.arms["A_aggregato"]
    n = b.regret_per_episode.shape[0]
    beneficio = (a.regret_mean - b.regret_mean) * n * VALORE_UNITA_RIMPIANTO
    mib = (b.bytes_retained - a.bytes_retained) / (1024 * 1024)
    ms = (b.query_seconds - a.query_seconds) * 1000.0
    costo = mib * COSTO_PER_MIB + ms * COSTO_PER_MS
    return beneficio, costo, beneficio > costo


def riga(c: Comparison) -> str:
    b = c.arms["B_pct"]
    a = c.arms["A_aggregato"]
    p = c.arms["C_parametrico"]
    z = c.arms["P0_niente"]
    d_a, lo_a, hi_a = c.paired["B_vs_A_aggregato"]
    d_c, lo_c, hi_c = c.paired["B_vs_C_parametrico"]
    signif_a = "SI" if hi_a < 0 else ("PEGGIO" if lo_a > 0 else "no")
    signif_c = "SI" if hi_c < 0 else ("PEGGIO" if lo_c > 0 else "no")
    rel = (a.regret_mean - b.regret_mean) / a.regret_mean * 100 if a.regret_mean else 0.0
    return (f"{c.phenomenon:<12} {z.regret_mean:7.4f} {a.regret_mean:8.4f} "
            f"{p.regret_mean:8.4f} {b.regret_mean:8.4f} "
            f"{rel:+7.1f}% {signif_a:>6} {signif_c:>6}")


def verdetto(c: Comparison) -> str:
    d_a, lo_a, hi_a = c.paired["B_vs_A_aggregato"]
    vince = hi_a < 0
    atteso = c.phenomenon in ATTESO_VINCE_B
    if vince and atteso:
        return "come previsto: B vince dove c'e' una condizione osservabile"
    if vince and not atteso:
        return "INATTESO: B vince dove non dovrebbe -- indagare prima di festeggiare"
    if not vince and atteso:
        return "INATTESO: B non vince dove dovrebbe -- l'ipotesi perde terreno"
    return "come previsto: nessun vantaggio"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=200_000)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--phenomena", type=str, default=",".join(FENOMENI))
    args = ap.parse_args(argv)

    scelti = [f.strip() for f in args.phenomena.split(",") if f.strip()]

    print(f"\nPCT -- esperimento §9   episodi={args.episodes}  seed={args.seed}")
    print("rimpianto medio per episodio (piu' basso e' meglio)\n")
    print(f"{'fenomeno':<12} {'P0':>7} {'A aggr':>8} {'C param':>8} {'B prec':>8} "
          f"{'B vs A':>8} {'sig A':>6} {'sig C':>6}")
    print("-" * 78)

    risultati = []
    for f in scelti:
        c = run_phenomenon(None if f == "nessuno" else f,
                           seed=args.seed, n_episodes=args.episodes)
        risultati.append(c)
        print(riga(c))

    print("\nverdetti rispetto alle predizioni dichiarate prima del run:")
    for c in risultati:
        print(f"  {c.phenomenon:<12} {verdetto(c)}")

    print("\npareggio costo/beneficio (spec §10.1), nelle unita' dichiarate in cima:")
    print(f"  {'fenomeno':<14} {'beneficio':>11} {'costo':>10}   esito")
    for c in risultati:
        ben, cost, ok = pareggio(c)
        print(f"  {c.phenomenon:<14} {ben:11.1f} {cost:10.1f}   "
              f"{'conviene' if ok else 'NON conviene'}")

    print("\ncondizioni ammesse dal fold di struttura (quota di stati):")
    for c in risultati:
        print(f"  {c.phenomenon:<14} d={c.cond_d:5.1%}   e={c.cond_e:5.1%}")

    print("\ncosto conservato (ledger, spec §10.1):")
    for c in risultati[:1]:
        for nome in ("A_aggregato", "C_parametrico", "B_pct"):
            a = c.arms[nome]
            print(f"  {nome:<14} {a.bytes_retained/1024:9.1f} KiB   "
                  f"build {a.build_seconds*1000:7.1f} ms   "
                  f"query {a.query_seconds*1000:8.1f} ms   "
                  f"NO_EVIDENCE {a.no_evidence_rate:5.1%}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
