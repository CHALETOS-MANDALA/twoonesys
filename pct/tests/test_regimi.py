"""I regimi in cui B DEVE vincere, e quelli in cui NON deve.

Sono i test che le mutazioni devono uccidere: se il condizionamento o gli eventi
rari smettono di funzionare, questi devono diventare rossi. Un test che resta
verde dopo aver rotto la proprieta' che dichiara di coprire e' teatro.

Predizioni dichiarate PRIMA del run definitivo:
  vince  -> effect_flip (condizione osservabile che inverte l'effetto)
            catastrophe (evento raro condizionato, invisibile nella media)
  pari   -> nessuno, confound (contro un aggregato FORTE la propensione basta),
            drift (regime che cambia senza marcatore osservabile: vederlo
            richiederebbe una pesatura per recency, che la carta vieta)
"""

from __future__ import annotations

import numpy as np
import pytest

from runner import run_phenomenon

N = 120_000
SEED = 4242


@pytest.fixture(scope="module")
def flip():
    return run_phenomenon("effect_flip", seed=SEED, n_episodes=N)


@pytest.fixture(scope="module")
def cata():
    return run_phenomenon("catastrophe", seed=SEED, n_episodes=N)


@pytest.fixture(scope="module")
def piano():
    return run_phenomenon(None, seed=SEED, n_episodes=N)


def test_B_vince_su_effect_flip(flip):
    """Il condizionamento su una condizione osservabile deve pagare."""
    b = flip.arms["B_pct"].regret_mean
    a = flip.arms["A_aggregato"].regret_mean
    _, lo, hi = flip.paired["B_vs_A_aggregato"]
    assert hi < 0, f"B non batte A: diff IC95=({lo:.4f},{hi:.4f})"
    assert b < 0.5 * a, f"vantaggio troppo piccolo: B={b:.4f} A={a:.4f}"


def test_B_evita_la_catastrofe(cata):
    """B deve usare a2 dove e' sicura e astenersi dove non lo e'.

    Nota onesta: A si astiene OVUNQUE (0 catastrofi) e per questo perde valore
    nei casi facili, dove a2 e' davvero la scelta migliore. Il vantaggio di B e'
    l'esclusione CONDIZIONATA, e si legge sul rimpianto -- che gia' include il
    costo della catastrofe nella magnitudine. Il conteggio delle catastrofi resta
    come diagnostica del rischio di coda che B accetta.
    """
    b = cata.arms["B_pct"]
    a = cata.arms["A_aggregato"]
    _, lo, hi = cata.paired["B_vs_A_aggregato"]
    assert hi < 0, f"B non batte A sul rimpianto: IC95=({lo:.4f},{hi:.4f})"
    assert b.regret_mean < 0.7 * a.regret_mean
    # il rischio di coda accettato resta piccolo in assoluto
    n = b.regret_per_episode.shape[0]
    assert b.catastrophe_expected / n < 1e-4, (
        f"B accetta troppe catastrofi: {b.catastrophe_expected:.2f} su {n} episodi")


def test_a2_sembra_la_scelta_giusta_nel_banco_catastrofe(cata):
    """Senza questo, la policy evita a2 comunque e non si misura niente."""
    from world import A_CATASTROPHIC, World, with_only
    w = World(with_only("catastrophe", seed=SEED, n_episodes=1_000))
    marcati = np.flatnonzero(w._catastrophic_states)
    assert marcati.size > 0
    piu_alto = 0
    for s in marcati:
        p = [float(w.p_success(np.array([s]), np.array([a]), np.array([0]),
                               np.array([0]), np.array([0]))[0]) for a in range(3)]
        if int(np.argmax(p)) == A_CATASTROPHIC:
            piu_alto += 1
    assert piu_alto == marcati.size, (
        "a2 deve avere il tasso di successo piu' alto negli stati marcati: "
        "altrimenti la policy la scarta comunque")


def test_la_catastrofe_colpisce_solo_i_casi_difficili():
    from world import World, with_only
    ep = World(with_only("catastrophe", seed=SEED, n_episodes=300_000)).generate()
    colpiti = ep.magnitude < -100
    assert colpiti.sum() > 10, "troppe poche catastrofi per concludere"
    assert (ep.d[colpiti] == 1).all(), "devono avvenire solo nei casi difficili"


def test_nessun_vantaggio_dove_non_deve_essercene(piano):
    _, lo, hi = piano.paired["B_vs_A_aggregato"]
    assert lo <= 0.0 <= hi, (
        f"B vince dove non dovrebbe: IC95=({lo:.4f},{hi:.4f}) -- indagare")


def test_drift_non_da_vantaggio_a_B():
    """Un regime che cambia senza marcatore osservabile e' invisibile anche a B.

    Se questo test diventasse rosso, qualcuno ha introdotto una pesatura
    temporale: e' un ranking, e viola la carta §7.
    """
    c = run_phenomenon("drift", seed=SEED, n_episodes=N)
    _, lo, hi = c.paired["B_vs_A_aggregato"]
    assert lo <= 0.0 <= hi, (
        "B mostra un vantaggio su drift: verificare che non sia stata introdotta "
        "una pesatura per recency")


def test_B_non_peggiora_su_confound():
    """Contro un aggregato FORTE la propensione basta: B deve pareggiare.

    Se B usasse la media invece di Hajek, qui perderebbe: e' il test che rende
    load-bearing lo stimatore dentro il provider, non solo in estimators.py.
    """
    c = run_phenomenon("confound", seed=SEED, n_episodes=N)
    _, lo, hi = c.paired["B_vs_A_aggregato"]
    assert lo <= 0.0, f"B peggiora su confound: IC95=({lo:.4f},{hi:.4f})"
    b = c.arms["B_pct"].regret_mean
    a = c.arms["A_aggregato"].regret_mean
    assert b <= a * 1.05, f"B={b:.4f} peggio di A={a:.4f}"


def test_orizzonte_dichiarato_cambia_l_azione_ottima():
    """Spec §5.1: misurare a T+0 invece che a T+N sceglie l'azione sbagliata."""
    from world import A_DELAYED, World, with_only
    w = World(with_only("delay", seed=SEED, n_episodes=1_000))
    s = np.arange(32)
    zero = np.zeros(32, dtype=np.int64)
    imm = np.stack([w.true_value(s, np.full(32, a), zero, zero, zero, horizon=False)
                    for a in range(3)])
    orz = np.stack([w.true_value(s, np.full(32, a), zero, zero, zero, horizon=True)
                    for a in range(3)])
    diverse = (imm.argmax(axis=0) != orz.argmax(axis=0)).sum()
    assert diverse > 0, "l'orizzonte non cambia mai la scelta: il fenomeno e' inerte"
    assert (imm.argmax(axis=0) == A_DELAYED).sum() > (
        orz.argmax(axis=0) == A_DELAYED).sum(), (
        "a1 deve sembrare migliore nell'immediato che all'orizzonte")


def test_il_contratto_di_misura_e_registrato():
    from world import World, with_only, OUTCOME_CONTRACT_ORIZZONTE
    ep = World(with_only("delay", seed=1, n_episodes=1_000)).generate()
    assert ep.outcome_contract == OUTCOME_CONTRACT_ORIZZONTE
    assert ep.state_function_digest
    assert ep.ledger_ref.shape[0] == len(ep)
