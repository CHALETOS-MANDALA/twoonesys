"""Quali condizioni meritano di essere usate -- e nient'altro (carta rev. 3 §4.2).

La regola della carta e' esplicita e io non l'avevo implementata: una condizione
entra SOLO se **cambia l'effetto relativo delle azioni**, non se cambia il tasso
di successo e non "sempre".

Condizionare non e' gratis: dimezza il supporto della cella, allarga gli errori
standard e rende la policy piu' timida (attacco 10, positivita'). Condizionare
quando non serve peggiora le decisioni -- misurato, non ipotizzato.

Il criterio e' una differenza-nelle-differenze fra livelli della condizione:

    DiD(a,b) = [V(a|v=1) - V(b|v=1)] - [V(a|v=0) - V(b|v=0)]

la condizione serve se |DiD| supera z errori standard per almeno una coppia.

Si stima sul fold di STRUTTURA e si congela: mai sul fold su cui poi si stima, e
mai su quello di valutazione (attacco 11, leakage).

La struttura ha DUE ingressi, e vanno tenuti separati perche' hanno natura diversa:

  1. SELEZIONE STATISTICA (DiD + bootstrap di stabilita'): ammette una condizione
     solo se il cambio di effetto sopravvive al ricampionamento.

  2. REGOLA DICHIARATA sugli eventi rari: se gli eventi catastrofici si
     concentrano in un livello della condizione, la condizione entra -- senza
     passare dal bootstrap. Due ragioni: (a) tecnica, lo stesso evento che sposta
     la media gonfia l'errore standard, quindi la DiD non lo rilevera' mai;
     (b) di dominio, e piu' importante: per una magnitudine catastrofica UN caso
     basta -- e' l'utilita' dichiarata (carta §5.2) che parla, non la
     significativita'.

Ciascuno e' implementato in UN SOLO posto. Una versione precedente li aveva
duplicati, e una mutazione e' sopravvissuta perche' rompeva solo una delle due
copie: sembrava che il meccanismo non servisse, mentre serviva eccome
(togliendolo del tutto: cond_d 9.4% -> 0.0%, e B perde tutto il vantaggio in
CATASTROPHE). La lezione e' nel cancello di mutazione, non nel ragionamento.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from estimators import hajek
from evidence import assert_pre_decision
from world import N_ACTIONS, N_STATES, Episodes

Z_DID: float = 2.0
MIN_PER_LIVELLO: int = 40
SOGLIA_STABILITA: float = 0.80
SOGLIA_RARO: float = 100.0        # oltre questa magnitudine l'evento e' "raro"
CONCENTRAZIONE_MIN: float = 0.90  # quota di eventi rari in un solo livello
MIN_EVENTI_RARI: int = 1          # per una catastrofe, uno basta (regola dichiarata)


@dataclass(frozen=True)
class StateStructure:
    """Per ogni stato, quali condizioni sono state ammesse."""

    use_d: np.ndarray   # (N_STATES,) bool
    use_e: np.ndarray   # (N_STATES,) bool
    digest: str         # identita' della funzione di stato (carta §4.5)

    def level(self, state: int) -> str:
        d, e = bool(self.use_d[state]), bool(self.use_e[state])
        if d and e:
            return "stato+d+e"
        if e:
            return "stato+e"
        if d:
            return "stato+d"
        return "stato"


def _valori_per_livello(ep: Episodes, in_s: np.ndarray, var: np.ndarray,
                        livello: int) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    m0 = in_s & (var == livello)
    for a in range(N_ACTIONS):
        m = m0 & (ep.action == a)
        if int(m.sum()) < MIN_PER_LIVELLO:
            continue
        est = hajek(ep.magnitude[m], ep.prop[m])
        if np.isfinite(est.std_err):
            out[a] = (est.value, est.std_err)
    return out


def _eventi_rari_concentrati(ep: Episodes, in_s: np.ndarray,
                             var: np.ndarray) -> bool:
    """Regola DICHIARATA (non inferenza): gli eventi catastrofici concentrati in
    un livello della condizione la rendono necessaria. Vedi la nota in testa."""
    raro = in_s & (np.abs(ep.magnitude) >= SOGLIA_RARO)
    if int(raro.sum()) < MIN_EVENTI_RARI:
        return False
    esposti = [int((in_s & (var == l)).sum()) for l in (0, 1)]
    if min(esposti) < MIN_PER_LIVELLO:
        return False
    livelli = var[raro]
    return max(float((livelli == l).mean()) for l in (0, 1)) >= CONCENTRAZIONE_MIN


def _condizione_serve(ep: Episodes, in_s: np.ndarray, var: np.ndarray) -> bool:
    v0 = _valori_per_livello(ep, in_s, var, 0)
    v1 = _valori_per_livello(ep, in_s, var, 1)
    comuni = sorted(set(v0) & set(v1))
    for a, b in combinations(comuni, 2):
        did = (v1[a][0] - v1[b][0]) - (v0[a][0] - v0[b][0])
        se = np.sqrt(v1[a][1] ** 2 + v1[b][1] ** 2 + v0[a][1] ** 2 + v0[b][1] ** 2)
        if se > 0 and abs(did) > Z_DID * se:
            return True
    return False


def learn_structure(struttura: Episodes, digest: str | None = None) -> StateStructure:
    """Decide, stato per stato, quali condizioni usare. Solo sul fold di struttura.

    Passa dalla guardia collider: si possono usare SOLO le condizioni dichiarate
    pre-decisione. Chiedere uno split su una variabile post-azione solleva.
    """
    for nome in ("d", "e"):
        assert_pre_decision(nome)
    digest = digest or struttura.state_function_digest
    use_d = np.zeros(N_STATES, dtype=bool)
    use_e = np.zeros(N_STATES, dtype=bool)
    for s in range(N_STATES):
        in_s = struttura.state == s
        if not in_s.any():
            continue
        use_d[s] = _condizione_serve(struttura, in_s, struttura.d)
        use_e[s] = _condizione_serve(struttura, in_s, struttura.e)
    return StateStructure(use_d=use_d, use_e=use_e, digest=digest)


def learn_structure_stable(struttura: Episodes, n_boot: int = 20, seed: int = 0,
                           soglia: float = SOGLIA_STABILITA,
                           digest: str | None = None) -> StateStructure:
    """Selezione per stabilita' (spec §10.3): una condizione entra solo se viene
    scelta in almeno `soglia` dei ricampionamenti del fold di struttura.

    E' questa la funzione che la pipeline deve usare: un singolo fit seleziona
    anche condizioni che il rumore avrebbe potuto produrre.
    """
    freq_d, freq_e = stability(struttura, n_boot=n_boot, seed=seed, digest=digest)
    use_d, use_e = freq_d >= soglia, freq_e >= soglia
    # secondo ingresso: la regola dichiarata sugli eventi rari, fuori dal bootstrap
    for s in range(N_STATES):
        in_s = struttura.state == s
        if not in_s.any():
            continue
        use_d[s] |= _eventi_rari_concentrati(struttura, in_s, struttura.d)
        use_e[s] |= _eventi_rari_concentrati(struttura, in_s, struttura.e)
    return StateStructure(use_d=use_d, use_e=use_e,
                          digest=digest or struttura.state_function_digest)


def stability(struttura: Episodes, n_boot: int = 20, seed: int = 0,
              digest: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Stability selection (spec §10.3): con che frequenza ogni condizione entra.

    Un campo si ammette solo con frequenza >= 0.80. Se nessuno la supera, la
    state_key non e' stabile su quel dominio: e' una falsificazione.
    """
    rng = np.random.default_rng(seed)
    n = len(struttura)
    conta_d = np.zeros(N_STATES)
    conta_e = np.zeros(N_STATES)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        st = learn_structure(struttura.take(idx), digest)
        conta_d += st.use_d
        conta_e += st.use_e
    return conta_d / n_boot, conta_e / n_boot
