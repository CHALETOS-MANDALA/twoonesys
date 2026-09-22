"""Test 1 e 2 della specifica: determinismo e validita' delle propensioni."""

from __future__ import annotations

import numpy as np
import pytest

from world import N_ACTIONS, N_STATES, WorldConfig, World, with_only

PHENOMENA = ("drift", "catastrophe", "confound", "effect_flip",
             "sparse", "low_support", "env_change", "delay")


# ------------------------------------------------------------------ test 1


def test_stesso_seed_stream_identico():
    cfg = WorldConfig(seed=7, n_episodes=5_000, confound=True, catastrophe=True)
    a = World(cfg).generate()
    b = World(cfg).generate()
    for name in ("state", "d", "e", "action", "prop", "success", "magnitude", "t"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name


def test_seed_diverso_stream_diverso():
    a = World(WorldConfig(seed=1, n_episodes=5_000)).generate()
    b = World(WorldConfig(seed=2, n_episodes=5_000)).generate()
    assert not np.array_equal(a.action, b.action)


@pytest.mark.parametrize("phenomenon", PHENOMENA)
def test_ogni_fenomeno_genera_e_resta_deterministico(phenomenon):
    cfg = with_only(phenomenon, seed=3, n_episodes=4_000)
    a = World(cfg).generate()
    b = World(cfg).generate()
    assert len(a) == 4_000
    assert np.array_equal(a.magnitude, b.magnitude)


# ------------------------------------------------------------------ test 2


@pytest.mark.parametrize("phenomenon", PHENOMENA)
def test_propensioni_sommano_a_uno(phenomenon):
    cfg = with_only(phenomenon, seed=5, n_episodes=3_000)
    w = World(cfg)
    ep = w.generate()
    probs = w.behaviour_probs(ep.state, ep.d)
    assert probs.shape == (len(ep), N_ACTIONS)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-12)


@pytest.mark.parametrize("phenomenon", PHENOMENA)
def test_propensione_registrata_e_quella_usata(phenomenon):
    """La propensita' nel record deve essere P(azione scelta | stato, d)."""
    cfg = with_only(phenomenon, seed=11, n_episodes=3_000)
    w = World(cfg)
    ep = w.generate()
    probs = w.behaviour_probs(ep.state, ep.d)
    attesa = probs[np.arange(len(ep)), ep.action]
    np.testing.assert_allclose(ep.prop, attesa, atol=1e-12)


@pytest.mark.parametrize("phenomenon", PHENOMENA)
def test_positivita_nessuna_propensione_nulla(phenomenon):
    cfg = with_only(phenomenon, seed=13, n_episodes=3_000)
    ep = World(cfg).generate()
    assert (ep.prop > 0.0).all()


def test_low_support_crea_supporto_povero_senza_azzerarlo():
    """LOW_SUPPORT deve stressare il supporto, non violare la positivita'."""
    cfg = with_only("low_support", seed=17, n_episodes=20_000)
    ep = World(cfg).generate()
    assert ep.prop.min() > 0.0
    assert ep.prop.max() > 0.99          # esiste la cella quasi-deterministica
    assert ep.prop.min() < 0.01          # e la sua coda rarissima


def test_confound_lega_la_scelta_alla_difficolta():
    """Senza questo legame, il test 3 non avrebbe niente da separare.

    Va misurato PER STATO sull'azione preferita di quello stato: l'azione
    preferita cambia da stato a stato, quindi sulla marginale il legame si
    diluisce e non si vedrebbe.
    """
    def divario_medio(cfg) -> float:
        w = World(cfg)
        ep = w.generate()
        divari = []
        for s in range(N_STATES):
            a = int(w._preferred[s])
            facili = ep.d[ep.state == s] == 0
            scelte = ep.action[ep.state == s] == a
            if facili.sum() < 100 or (~facili).sum() < 100:
                continue
            divari.append(scelte[facili].mean() - scelte[~facili].mean())
        return float(np.mean(divari))

    senza = divario_medio(with_only(None, seed=19, n_episodes=60_000))
    con = divario_medio(with_only("confound", seed=19, n_episodes=60_000))

    assert abs(senza) < 0.02, "senza confound la scelta non deve dipendere da d"
    assert con > 0.40, "con confound i casi facili devono ricevere l'azione preferita"


def test_stati_e_azioni_nel_dominio():
    ep = World(WorldConfig(seed=23, n_episodes=5_000)).generate()
    assert ep.state.min() >= 0 and ep.state.max() < N_STATES
    assert ep.action.min() >= 0 and ep.action.max() < N_ACTIONS
    assert set(np.unique(ep.d)) <= {0, 1}
    assert set(np.unique(ep.e)) <= {0, 1}


def test_env_change_commuta_una_sola_volta():
    cfg = with_only("env_change", seed=29, n_episodes=10_000)
    ep = World(cfg).generate()
    cambi = np.flatnonzero(np.diff(ep.e) != 0)
    assert cambi.shape[0] == 1
    assert ep.e[0] == 0 and ep.e[-1] == 1


def test_catastrofe_e_rara_e_solo_su_a2():
    cfg = with_only("catastrophe", seed=31, n_episodes=200_000)
    ep = World(cfg).generate()
    colpite = ep.magnitude < -100
    assert colpite.any(), "il fenomeno deve manifestarsi almeno una volta"
    assert (ep.action[colpite] == 2).all(), "solo a2 puo' essere catastrofica"
    assert colpite.mean() < 0.01, "deve restare un evento raro"


def test_senza_il_fenomeno_nessuna_catastrofe():
    ep = World(WorldConfig(seed=31, n_episodes=50_000)).generate()
    assert (ep.magnitude >= -1.0).all()
