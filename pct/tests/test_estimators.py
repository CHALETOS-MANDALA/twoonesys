"""Test 3 della specifica -- il cancello del progetto.

Con CONFOUND acceso lo stimatore Hajek deve recuperare il valore vero marginale,
e la media semplice NO. Se questi due non si separano, il mondo non ha
confondimento e l'esperimento non sta testando cio' che crede: non si prosegue.
"""

from __future__ import annotations

import numpy as np
import pytest

from estimators import (effective_sample_size, hajek,
                        lower_confidence_bound, naive_mean)
from world import N_ACTIONS, N_STATES, World, WorldConfig, with_only

N_GRANDE = 400_000


def _errori_per_cella(cfg: WorldConfig) -> tuple[np.ndarray, np.ndarray]:
    """Errore assoluto di Hajek e della media, per ogni (stato, azione)."""
    w = World(cfg)
    ep = w.generate()
    err_h, err_n = [], []
    for s in range(N_STATES):
        in_s = ep.state == s
        for a in range(N_ACTIONS):
            m = in_s & (ep.action == a)
            if m.sum() < 200:
                continue
            vero = w.marginal_true_value(s, a, e=0, t=0)
            err_h.append(abs(hajek(ep.magnitude[m], ep.prop[m]).value - vero))
            err_n.append(abs(naive_mean(ep.magnitude[m]).value - vero))
    return np.array(err_h), np.array(err_n)


def test_3_hajek_recupera_la_verita_la_media_no():
    """IL test. Con confondimento, i due stimatori DEVONO separarsi."""
    err_h, err_n = _errori_per_cella(
        with_only("confound", seed=101, n_episodes=N_GRANDE))

    assert err_h.size > 50, "troppe poche celle popolate per concludere"

    mae_h, mae_n = float(err_h.mean()), float(err_n.mean())

    # Hajek deve essere vicino alla verita' in assoluto...
    assert mae_h < 0.03, f"Hajek non recupera la verita': MAE={mae_h:.4f}"
    # ...e la media semplice deve essere nettamente peggiore.
    assert mae_n > 2.0 * mae_h, (
        f"nessuna separazione: Hajek MAE={mae_h:.4f} media MAE={mae_n:.4f}. "
        "Il mondo non ha confondimento utile: l'esperimento non testa cio' che crede.")


def test_senza_confondimento_i_due_stimatori_coincidono():
    """Controllo negativo: senza confound la media semplice e' gia' corretta."""
    err_h, err_n = _errori_per_cella(
        with_only(None, seed=101, n_episodes=N_GRANDE))
    mae_h, mae_n = float(err_h.mean()), float(err_n.mean())
    assert mae_h < 0.03 and mae_n < 0.03
    assert abs(mae_h - mae_n) < 0.02, "senza confondimento non devono separarsi"


def test_la_distorsione_della_media_ha_il_segno_atteso():
    """L'azione preferita nei casi facili deve sembrare migliore del vero."""
    cfg = with_only("confound", seed=103, n_episodes=N_GRANDE)
    w = World(cfg)
    ep = w.generate()
    scarti = []
    for s in range(N_STATES):
        a = int(w._preferred[s])
        m = (ep.state == s) & (ep.action == a)
        if m.sum() < 200:
            continue
        vero = w.marginal_true_value(s, a, e=0, t=0)
        scarti.append(naive_mean(ep.magnitude[m]).value - vero)
    scarti = np.array(scarti)
    assert scarti.size > 20
    assert scarti.mean() > 0.10, (
        "la media semplice deve SOVRASTIMARE l'azione preferita nei casi facili")


# ------------------------------------------------------- proprieta' di base


def test_ess_con_pesi_uguali_vale_n():
    w = np.full(500, 3.0)
    assert effective_sample_size(w) == pytest.approx(500.0)


def test_ess_crolla_con_pesi_squilibrati():
    w = np.concatenate([np.ones(999), np.array([10_000.0])])
    assert effective_sample_size(w) < 5.0


def test_hajek_rifiuta_propensione_nulla():
    with pytest.raises(ValueError, match="positivita'"):
        hajek(np.array([1.0, -1.0]), np.array([0.5, 0.0]))


def test_hajek_resta_nell_intervallo_delle_osservazioni():
    rng = np.random.default_rng(0)
    mag = rng.choice([-1.0, 1.0], size=10_000)
    prop = rng.uniform(0.01, 1.0, size=10_000)
    est = hajek(mag, prop)
    assert -1.0 <= est.value <= 1.0


def test_cella_vuota_non_esplode():
    vuoto = np.array([], dtype=float)
    assert np.isnan(naive_mean(vuoto).value)
    assert np.isnan(hajek(vuoto, vuoto).value)
    assert lower_confidence_bound(naive_mean(vuoto)) == float("-inf")


def test_lcb_e_sotto_la_stima():
    rng = np.random.default_rng(1)
    mag = rng.choice([-1.0, 1.0], size=2_000)
    est = naive_mean(mag)
    assert lower_confidence_bound(est) < est.value


def test_catastrofe_sposta_la_stima_di_valore():
    """Un evento raro enorme deve pesare: e' il punto di outcome_magnitude."""
    cfg = with_only("catastrophe", seed=107, n_episodes=N_GRANDE)
    w = World(cfg)
    ep = w.generate()
    colpiti = np.flatnonzero(ep.magnitude < -100)
    assert colpiti.size > 0
    s = int(ep.state[colpiti[0]])
    m = (ep.state == s) & (ep.action == 2)
    con = naive_mean(ep.magnitude[m]).value
    senza = naive_mean(ep.magnitude[m][ep.magnitude[m] > -100]).value
    assert con < senza - 0.5, "la catastrofe deve dominare la media della cella"
