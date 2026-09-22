"""Braccio B -- PCT: gli episodi conservati (spec §2.2).

Due sole cose che l'aggregato non puo' fare, e sono l'intera ipotesi:

  1. RI-CONDIZIONARE a posteriori su condizioni che nessuno aveva dichiarato
     nella state_key -- qui `e` e `d`;
  2. ESIBIRE l'evento raro invece di annegarlo nella media.

Gerarchia di condizionamento DICHIARATA (non un punteggio, carta §7):
        (stato, d, e)  ->  (stato, e)  ->  (stato)
Si scende di livello solo quando il supporto effettivo e' insufficiente.

NOTA IMPORTANTE, e volutamente non aggirata: B non usa il tempo come peso.
Un regime che cambia SENZA una condizione osservabile che lo marchi (il
fenomeno DRIFT) e' invisibile anche a B, perche' vederlo richiederebbe una
pesatura per recency -- che la carta vieta, essendo un ranking. Se B vincesse
su DRIFT, ci sarebbe un errore da qualche parte.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from estimators import hajek
from evidence import (ActionEvidence, Conditions, Evidence, RareEvent,
                      empty_if_starved)
from structure import StateStructure
from world import (ELIGIBLE_FOR_EXPLORATION, N_ACTIONS, N_STATES,
                   Episodes)


class PrecedentProvider:
    """Conserva gli episodi e stima al momento della richiesta, non prima."""

    name = "B_pct"

    def __init__(self, episodes: Episodes, structure: StateStructure,
                 ess_min: float = 30.0, rare_threshold: float = 100.0) -> None:
        self.ess_min = ess_min
        self.rare_threshold = rare_threshold
        self._ep = episodes
        self._st = structure

        # indice per (stato, azione) -> posizioni: e' il lookup in griglia finita
        self._idx: dict[tuple[int, int], np.ndarray] = {}
        for s in range(N_STATES):
            in_s = np.flatnonzero(episodes.state == s)
            if in_s.size == 0:
                continue
            act = episodes.action[in_s]
            for a in range(N_ACTIONS):
                sel = in_s[act == a]
                if sel.size:
                    self._idx[(s, a)] = sel

        # eventi rari conservati per (stato, azione): NON mediati
        self._rare: dict[tuple[int, int], tuple[RareEvent, ...]] = {}
        big = np.flatnonzero(np.abs(episodes.magnitude) >= rare_threshold)
        for i in big:
            key = (int(episodes.state[i]), int(episodes.action[i]))
            ev = RareEvent(action=int(episodes.action[i]),
                           magnitude=float(episodes.magnitude[i]),
                           conditions=Conditions(d=int(episodes.d[i]),
                                                 e=int(episodes.e[i]),
                                                 t=int(episodes.t[i])))
            self._rare[key] = self._rare.get(key, ()) + (ev,)

    def _livelli(self, state: int) -> tuple[str, ...]:
        """Solo le condizioni AMMESSE dal fold di struttura, poi il ripiego."""
        pieno = self._st.level(state)
        if pieno == "stato":
            return ("stato",)
        if pieno == "stato+d+e":
            return ("stato+d+e", "stato+e", "stato")
        return (pieno, "stato")

    def _mask(self, pos: np.ndarray, livello: str, cond: Conditions) -> np.ndarray:
        ep = self._ep
        if livello == "stato":
            return pos
        if livello == "stato+e":
            return pos[ep.e[pos] == cond.e]
        if livello == "stato+d":
            return pos[ep.d[pos] == cond.d]
        return pos[(ep.e[pos] == cond.e) & (ep.d[pos] == cond.d)]

    def query(self, state: int, eligible: Sequence[int],
              conditions: Conditions) -> Evidence:
        ep = self._ep
        # gli eventi rari si filtrano sulle stesse condizioni ammesse dalla
        # struttura: una catastrofe che avviene solo nei casi difficili non deve
        # escludere l'azione nei casi facili
        rare: tuple[RareEvent, ...] = ()
        usa_d = bool(self._st.use_d[state])
        usa_e = bool(self._st.use_e[state])
        for a in eligible:
            for ev in self._rare.get((state, a), ()):
                if usa_d and ev.conditions.d != conditions.d:
                    continue
                if usa_e and ev.conditions.e != conditions.e:
                    continue
                rare += (ev,)

        for livello in self._livelli(state):
            per_action: dict[int, ActionEvidence] = {}
            for a in eligible:
                pos = self._idx.get((state, a))
                if pos is None:
                    continue
                sel = self._mask(pos, livello, conditions)
                if sel.size == 0:
                    continue
                est = hajek(ep.magnitude[sel], ep.prop[sel])
                per_action[a] = ActionEvidence(value_hat=est.value, ess=est.ess,
                                               n=est.n, std_err=est.std_err)
            if per_action and any(v.ess >= self.ess_min for v in per_action.values()):
                unknown = tuple(a for a in eligible if a not in per_action
                                and a not in ELIGIBLE_FOR_EXPLORATION)
                return empty_if_starved(per_action, self.ess_min, rare, livello,
                                        unknown)

        unknown = tuple(a for a in eligible
                        if (state, a) not in self._idx
                        and a not in ELIGIBLE_FOR_EXPLORATION)
        return empty_if_starved({}, self.ess_min, rare, "stato", unknown)
