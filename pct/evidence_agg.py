"""Braccio A -- l'aggregato, nella sua versione PIU' FORTE (spec §2.1).

A NON e' una media ingenua: riceve la stessa correzione di propensione di B
(Hajek). E' deliberato: se l'avversario fosse debole, la vittoria di B non
direbbe niente sull'informazione episodica.

Cio' che A non puo' fare, ed e' tutta l'ipotesi del progetto:
  - ri-condizionare a posteriori su d o e, perche' sono gia' stati sommati via;
  - esibire il singolo episodio catastrofico, perche' e' annegato nella media.
"""

from __future__ import annotations

from typing import Sequence

from estimators import hajek
from evidence import ActionEvidence, Conditions, Evidence, empty_if_starved
from world import (ELIGIBLE_FOR_EXPLORATION, N_ACTIONS, N_STATES,
                   Episodes)


class AggregateProvider:
    """Tabella (stato, azione) -> valore Hajek, ESS, n. Nessuna condizione."""

    name = "A_aggregato"

    def __init__(self, episodes: Episodes, ess_min: float = 30.0) -> None:
        self.ess_min = ess_min
        self._table: dict[tuple[int, int], ActionEvidence] = {}
        for s in range(N_STATES):
            in_s = episodes.state == s
            if not in_s.any():
                continue
            for a in range(N_ACTIONS):
                m = in_s & (episodes.action == a)
                k = int(m.sum())
                if k == 0:
                    continue
                est = hajek(episodes.magnitude[m], episodes.prop[m])
                self._table[(s, a)] = ActionEvidence(
                    value_hat=est.value, ess=est.ess, n=est.n, std_err=est.std_err)

    def query(self, state: int, eligible: Sequence[int],
              conditions: Conditions) -> Evidence:
        # `conditions` arriva ma non puo' essere usata: l'informazione non esiste piu'
        per_action = {a: self._table[(state, a)]
                      for a in eligible if (state, a) in self._table}
        # un'azione senza dati e NON esplorabile non si potra' mai conoscere:
        # va dichiarata UNKNOWN invece di essere silenziosamente omessa (carta §7.1)
        unknown = tuple(a for a in eligible
                        if a not in per_action and a not in ELIGIBLE_FOR_EXPLORATION)
        return empty_if_starved(per_action, self.ess_min, (), "stato", unknown)
