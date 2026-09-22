"""Test del Motore Causale (Layer 1)."""

import pytest

from cascade.causal_engine import (
    CPD,
    CausalModel,
    CausalNode,
    sprinkler_model,
)


def test_add_cycle_detected():
    m2 = CausalModel()
    m2.add_variable(CausalNode("x", values=[0, 1]))
    m2.add_variable(CausalNode("y", cpd=CPD("y", ["x"], {(0,): {0: 1.0, 1: 0.0}, (1,): {0: 0.0, 1: 1.0}}), values=[0, 1]), parents=["x"])
    x_node = CausalNode("x", values=[0, 1])
    with pytest.raises(ValueError):
        m2.add_variable(x_node, parents=["y"])  # ciclo x->y->x


def test_posterior_normalizes():
    m = sprinkler_model()
    p = m.posterior("bagnato")
    assert abs(sum(p.values()) - 1.0) < 1e-9
    pwet = m.posterior("bagnato", {"bagnato": True})
    assert abs(pwet[True] - 1.0) < 1e-9


def test_do_mutilates_parents():
    m = sprinkler_model()
    # senza intervento, P(bagnato=True) alto
    base = m.posterior("bagnato")[True]
    # con sprinkler forzato OFF e pioggia assente, bagnato e' quasi impossibile
    intervened = m.mutilated({"sprinkler": False, "pioggia": False})
    p = intervened.posterior("bagnato")
    assert p[False] > 0.99


def test_do_ignores_correlation():
    m = sprinkler_model()
    # Causalità: intervenire su sprinkler non cambia pioggia (sono indipendenti)
    # correlando solo tramite effetto comune bagnato.
    posterior_pioggia_cond = m.posterior("pioggia", {"bagnato": True})
    # do(sprinkler) non deve influenzare la distribuzione di pioggia
    p_do_rain = m.do("pioggia", {"sprinkler": False})
    assert abs(p_do_rain[True] - 0.5) < 1e-9


def test_counterfactual_sanity():
    m = sprinkler_model()
    # Data bagnato=True, se avessimo spento la pioggia il prato
    # sarebbe rimasto bagnato solo se lo sprinkler era attivo.
    cf = m.counterfactual("bagnato", {"pioggia": False}, {"bagnato": True})
    # deve essere una distribuzione valida
    assert abs(sum(cf.values()) - 1.0) < 1e-9
    # abduzione: dato bagnato True, sprinkler spesso attivo -> bagnato resta probabile
    assert cf[True] > 0.5


def test_impossible_evidence_raises():
    m = sprinkler_model()
    with pytest.raises(ZeroDivisionError):
        m.posterior("bagnato", {"bagnato": "impossibile"})


def test_counterfactual_matches_pearl_twin_on_functional_scm():
    """Per un modello STRUTTURALE FUNZIONALE (meccanismi deterministici), il
    controfattuale deve coincidere ESATTAMENTE col twin network di Pearl.

    Oracle analitico: con bagnato=True osservato, forzando do(pioggia=False)
    il prato resta bagnato IFF lo sprinkler era attivo:
      P(wet | do(rain=F), wet=True) = P(sprinkler=True | wet=True)
    """
    m = CausalModel()
    m.add_variable(CausalNode("pioggia", values=[True, False]))
    m.add_variable(CausalNode("sprinkler", values=[True, False]))
    m.add_variable(CausalNode("bagnato", cpd=CPD(
        "bagnato", ["pioggia", "sprinkler"],
        {
            (True, True): {True: 1.0, False: 0.0},
            (True, False): {True: 1.0, False: 0.0},
            (False, True): {True: 1.0, False: 0.0},
            (False, False): {True: 0.0, False: 1.0},
        },
    )), parents=["pioggia", "sprinkler"])
    oracle = m.posterior("sprinkler", {"bagnato": True})[True]
    cf = m.counterfactual("bagnato", {"pioggia": False}, {"bagnato": True})
    assert abs(cf[True] - oracle) < 1e-9


def test_counterfactual_documented_limit_on_stochastic_cpd():
    """Limite documentato: con CPD STOCASTICHE il controfattuale NON riusa lo
    stesso rumore esogeno del twin network (la meccanica viene ricampionata).
    Il test blocca una regressione silenziosa: il valore deve restare una
    previsione interventistica condizionata coerente (0..1), ed e' documentato
    che NON e' un twin SCM completo."""
    m = sprinkler_model()
    cf = m.counterfactual("bagnato", {"pioggia": False}, {"bagnato": True})
    assert 0.0 <= cf[True] <= 1.0
    assert abs(sum(cf.values()) - 1.0) < 1e-9
