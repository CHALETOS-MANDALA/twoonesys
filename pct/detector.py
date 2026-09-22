"""Rilevatore di fenomeni su un log REALE (spec §10.2).

Nessun mondo sintetico puo' dimostrare di somigliare al reale. Ma ogni fenomeno
si puo' MISURARE sul log vero, con la stessa matematica con cui qui viene
iniettato. La composizione onesta e':

    §9 da' il valore per unita' di fenomeno
    questo modulo da' quanto fenomeno c'e' nel dominio reale
    il prodotto e' la stima del valore atteso li'

Nessuna delle due meta' da sola dice niente.

Uso su un log JSONL con i campi della carta §10.1:
    python3 detector.py cascade/run/outcome_log.jsonl
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass
from enum import Enum

import numpy as np

from estimators import effective_sample_size, hajek, naive_mean

SOGLIA_RARO = 100.0


class Stato(str, Enum):
    """Tre valori, non due. `NON_OSSERVABILE` non e' `ASSENTE`.

    Confondere «il fenomeno non c'e'» con «non riesco a vederlo» e' il modo piu'
    veloce di concludere che un dominio non ha bisogno di PCT quando in
    realta' il log non registra il campo che servirebbe per accorgersene.
    """

    RILEVATO = "rilevato"
    ASSENTE = "assente"
    NON_OSSERVABILE = "non osservabile"


@dataclass(frozen=True)
class Diagnosi:
    fenomeno: str
    stato: Stato
    misura: float
    nota: str

    @property
    def presente(self) -> bool:
        return self.stato is Stato.RILEVATO


def _campo(righe: list[dict], nome: str, default=None):
    return np.array([r.get(nome, default) for r in righe])


def carica(path: str | pathlib.Path) -> list[dict]:
    righe = []
    with open(path, "r", encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if riga:
                righe.append(json.loads(riga))
    return righe


def rileva_confondimento(state, action, prop, y) -> Diagnosi:
    """Il confondimento si vede come divergenza fra media semplice e Hajek."""
    scarti = []
    for s in np.unique(state):
        for a in np.unique(action):
            m = (state == s) & (action == a)
            if m.sum() < 30 or np.any(prop[m] <= 0):
                continue
            scarti.append(abs(hajek(y[m], prop[m]).value - naive_mean(y[m]).value))
    if not scarti:
        return Diagnosi("CONFOUND", Stato.NON_OSSERVABILE, 0.0,
                        "supporto insufficiente per stimare")
    med = float(np.median(scarti))
    # NON "confondimento provato": una divergenza fra media e Hajek e' un SEGNALE
    # compatibile con selection bias. Da sola non dimostra causalmente niente.
    return Diagnosi("CONFOUND (segnale)",
                    Stato.RILEVATO if med > 0.05 else Stato.ASSENTE, med,
                    "divergenza mediana |Hajek - media| per cella")


def rileva_drift(state, action, y, t) -> Diagnosi:
    """Due finestre temporali: il valore per cella cambia?"""
    meta = np.median(t)
    scarti = []
    for s in np.unique(state):
        for a in np.unique(action):
            m = (state == s) & (action == a)
            prima, dopo = m & (t <= meta), m & (t > meta)
            if prima.sum() < 30 or dopo.sum() < 30:
                continue
            scarti.append(abs(y[prima].mean() - y[dopo].mean()))
    if not scarti:
        return Diagnosi("DRIFT", Stato.NON_OSSERVABILE, 0.0,
                        "supporto insufficiente per due finestre")
    med = float(np.median(scarti))
    return Diagnosi("DRIFT", Stato.RILEVATO if med > 0.10 else Stato.ASSENTE,
                    med, "scarto mediano fra due finestre")


def rileva_coda_pesante(y, magnitudini_vere: bool = True) -> Diagnosi:
    """Senza magnitudini dichiarate la coda pesante non PUO' esistere: e' cecita'."""
    if not magnitudini_vere:
        return Diagnosi("CATASTROPHE", Stato.NON_OSSERVABILE, 0.0,
                        "nessuna scala di costi: +1/-1 non puo' avere coda")
    quota = float((np.abs(y) >= SOGLIA_RARO).mean())
    return Diagnosi("CATASTROPHE", Stato.RILEVATO if quota > 0 else Stato.ASSENTE,
                    quota, f"quota di esiti con |magnitudine| >= {SOGLIA_RARO:g}")


def rileva_supporto_povero(state, action, prop) -> Diagnosi:
    ess = []
    for s in np.unique(state):
        for a in np.unique(action):
            m = (state == s) & (action == a)
            if m.sum() == 0 or np.any(prop[m] <= 0):
                continue
            ess.append(effective_sample_size(1.0 / prop[m]))
    if not ess:
        return Diagnosi("LOW_SUPPORT", Stato.NON_OSSERVABILE, 0.0,
                        "nessuna cella valutabile")
    quota = float((np.array(ess) < 30).mean())
    return Diagnosi("LOW_SUPPORT",
                    Stato.RILEVATO if quota > 0.10 else Stato.ASSENTE, quota,
                    "quota di celle con ESS < 30")


def rileva_sparsita(state) -> Diagnosi:
    conta = np.bincount(state.astype(int))
    conta = conta[conta > 0]
    if conta.size < 2:
        return Diagnosi("SPARSE", Stato.NON_OSSERVABILE, 0.0,
                        "una sola cella: la sparsita' non e' definita")
    quota = float((conta < 0.1 * conta.mean()).mean())
    return Diagnosi("SPARSE", Stato.RILEVATO if quota > 0.10 else Stato.ASSENTE,
                    quota, "quota di stati con meno del 10% degli episodi medi")


def rileva_effetto_variabile(state, action, y, cond, nome_cond) -> Diagnosi:
    """L'azione migliore differisce fra i livelli della condizione?"""
    diversi = totali = 0
    for s in np.unique(state):
        best = {}
        ok = True
        for l in np.unique(cond):
            vals = {}
            for a in np.unique(action):
                m = (state == s) & (action == a) & (cond == l)
                if m.sum() < 30:
                    ok = False
                    break
                vals[a] = y[m].mean()
            if not ok:
                break
            best[l] = max(vals, key=vals.get)
        if ok and len(best) > 1:
            totali += 1
            diversi += len(set(best.values())) > 1
    if totali == 0:
        return Diagnosi(f"EFFECT_FLIP[{nome_cond}]", Stato.NON_OSSERVABILE, 0.0,
                        "supporto insufficiente per confrontare i livelli")
    quota = diversi / totali
    return Diagnosi(f"EFFECT_FLIP[{nome_cond}]",
                    Stato.RILEVATO if quota > 0.10 else Stato.ASSENTE, quota,
                    f"quota di stati in cui l'azione migliore cambia con {nome_cond}")


def diagnostica(righe: list[dict], campo_condizione: str | None = None,
                magnitudini_vere: bool = True) -> list[Diagnosi]:
    state = _campo(righe, "state_key", 0)
    action = _campo(righe, "action", 0)
    prop = _campo(righe, "selection_probability", 0.0).astype(float)
    y = _campo(righe, "outcome_magnitude", 0.0).astype(float)
    t = _campo(righe, "t", 0)
    if np.all(t == 0):
        t = np.arange(len(righe))

    out = [rileva_coda_pesante(y, magnitudini_vere), rileva_sparsita(state)]
    if np.all(prop > 0):
        out.insert(0, rileva_confondimento(state, action, prop, y))
        out.append(rileva_supporto_povero(state, action, prop))
    else:
        out.insert(0, Diagnosi("CONFOUND (segnale)", Stato.NON_OSSERVABILE, 0.0,
                               "propensione mancante o nulla: mai diagnosticabile "
                               "su questi record"))
    out.append(rileva_drift(state, action, y, t))
    if campo_condizione:
        cond = _campo(righe, campo_condizione, 0)
        out.append(rileva_effetto_variabile(state, action, y, cond, campo_condizione))
    else:
        out.append(Diagnosi("EFFECT_FLIP", Stato.NON_OSSERVABILE, 0.0,
                            "nessuna condizione pre-decisione registrata"))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    righe = carica(argv[0])
    cond = argv[1] if len(argv) > 1 else None
    print(f"\nlog: {argv[0]}   record: {len(righe)}\n")
    print(f"{'fenomeno':<22} {'stato':>16} {'misura':>10}  nota")
    print("-" * 88)
    for d in diagnostica(righe, cond):
        print(f"{d.fenomeno:<22} {d.stato.value:>16} "
              f"{d.misura:10.4f}  {d.nota}")
    print("\nnessuno di questi numeri dice se PCT serve: dicono quanto "
          "fenomeno\nc'e' qui. Il valore per unita' di fenomeno viene da §9.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
