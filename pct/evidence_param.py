"""Braccio C -- il modello parametrico (spec §10.5).

E' l'avversario dell'attacco 8: usa le STESSE condizioni di B, ma le riassume in
parametri invece di conservare gli episodi. Se C eguaglia B, gli episodi sono un
modo costoso di fare una regressione, e la risposta corretta e' fare la
regressione.

Specificazione dichiarata, e va letta come un'assunzione esplicita:

    valore(a) ~ intercetta_stato + beta_d * d + beta_e * e + beta_de * d*e

Effetti principali di `d` ed `e` e la loro interazione, ma NESSUNA interazione
stato x ambiente. Rappresenta il modellatore che ha incluso cio' che si aspettava
e non l'inversione di effetto specifica per stato (EFFECT_FLIP). E' li' che C
dovrebbe perdere contro B, e in nessun altro posto: chi volesse rendere C piu'
forte aggiunga quell'interazione ed e' un esperimento legittimo -- il risultato
direbbe quanto del vantaggio di B era solo cattiva specificazione.

Stima ai minimi quadrati pesati per 1/propensita' (stessa correzione degli altri
bracci) con ridge per stabilita'.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from evidence import (ActionEvidence, Conditions, Evidence, empty_if_starved)
from world import (ELIGIBLE_FOR_EXPLORATION, N_ACTIONS, N_STATES,
                   Episodes)

RIDGE: float = 1.0


def _design(state: np.ndarray, d: np.ndarray, e: np.ndarray) -> np.ndarray:
    n = state.shape[0]
    x = np.zeros((n, N_STATES + 3), dtype=np.float64)
    x[np.arange(n), state] = 1.0
    x[:, N_STATES + 0] = d
    x[:, N_STATES + 1] = e
    x[:, N_STATES + 2] = d * e
    return x


class ParametricProvider:
    """Una regressione pesata per azione. Nessuna rete, pochi parametri."""

    name = "C_parametrico"

    def __init__(self, episodes: Episodes, ess_min: float = 30.0) -> None:
        self.ess_min = ess_min
        self._beta: dict[int, np.ndarray] = {}
        self._sigma: dict[int, float] = {}
        self._n_cell = np.zeros((N_STATES, N_ACTIONS), dtype=np.int64)

        for a in range(N_ACTIONS):
            m = episodes.action == a
            if m.sum() < N_STATES + 3:
                continue
            x = _design(episodes.state[m], episodes.d[m], episodes.e[m])
            y = episodes.magnitude[m]
            w = 1.0 / episodes.prop[m]
            sw = np.sqrt(w)
            xw, yw = x * sw[:, None], y * sw

            gram = xw.T @ xw + RIDGE * np.eye(x.shape[1])
            beta = np.linalg.solve(gram, xw.T @ yw)
            self._beta[a] = beta

            resid = y - x @ beta
            var = float((w * resid ** 2).sum() / w.sum())
            self._sigma[a] = float(np.sqrt(max(var, 1e-12)))

        for s in range(N_STATES):
            in_s = episodes.state == s
            for a in range(N_ACTIONS):
                self._n_cell[s, a] = int((in_s & (episodes.action == a)).sum())

    def query(self, state: int, eligible: Sequence[int],
              conditions: Conditions) -> Evidence:
        x = _design(np.array([state]), np.array([conditions.d]),
                    np.array([conditions.e]))
        per_action: dict[int, ActionEvidence] = {}
        for a in eligible:
            beta = self._beta.get(a)
            n = int(self._n_cell[state, a])
            if beta is None or n == 0:
                continue
            value = float((x @ beta)[0])
            se = self._sigma[a] / np.sqrt(n)
            per_action[a] = ActionEvidence(value_hat=value, ess=float(n), n=n,
                                           std_err=float(se))
        unknown = tuple(a for a in eligible
                        if a not in per_action and a not in ELIGIBLE_FOR_EXPLORATION)
        # il modello non conserva eventi rari: li ha mediati nei parametri
        return empty_if_starved(per_action, self.ess_min, (), "parametrico", unknown)
