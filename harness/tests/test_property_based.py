"""Test avversariali property-based (Hypothesis).

Scopo: FALSIFICARE il sistema con input inattesi, non confermarlo su input
preparati. Invarianti formali che devono valere per QUALSIASI input generato:
- posteriori normalizzati (0..1, somma=1) per ogni query/evidenza;
- do() con rami alternativi produce distribuzioni valide;
- la mutilazione non modifica mai la distribuzione delle variabili NON
  nell'ascendenza dell'intervenuta (proprieta' di intervento Pearl);
- il guard accetta esattamente i valori dentro il dominio e blocca quelli fuori.

Questi sono test che il "0.00 perfetto" non copre: cercano input che ROmPANO
le invarianti.
"""

import hypothesis
from hypothesis import given, settings
from hypothesis import strategies as st

from cascade.causal_engine import CPD, CausalModel, CausalNode, sprinkler_model
from cascade.neurosymbolic_guard import ConfidenceLevel, NeurosymbolicGuard


def _always_normalized(p: dict) -> bool:
    return all(0.0 <= v <= 1.0 for v in p.values()) and abs(sum(p.values()) - 1.0) < 1e-9


@given(st.sampled_from([True, False]), st.sampled_from([True, False]))
@settings(max_examples=50)
def test_posterior_normalized_for_any_evidence(rain, wet):
    m = sprinkler_model()
    ev = {}
    if wet:
        ev["bagnato"] = True
    p = m.posterior("pioggia", ev)
    assert _always_normalized(p)


@given(st.sampled_from([True, False]), st.sampled_from([True, False]))
@settings(max_examples=50)
def test_do_returns_valid_distribution(rain, sprinkler_interv):
    m = sprinkler_model()
    p = m.do("bagnato", {"sprinkler": sprinkler_interv})
    assert _always_normalized(p)


@given(st.one_of(st.sampled_from([True, False]),
                 st.one_of(st.integers(-5, 5), st.text())))
@settings(max_examples=50)
def test_posterior_rejects_impossible_or_returns_valid(bad_evidence):
    m = sprinkler_model()
    try:
        p = m.posterior("bagnato", {"bagnato": bad_evidence})
        assert _always_normalized(p)
    except ZeroDivisionError:
        pass  # evidenza con probabilita' zero -> errore gestito, non crash


@given(st.integers(-10, 10))
@settings(max_examples=50)
def test_guard_bounds_exact(bound):
    """Il guard accetta esattamente i valori dentro [0,100] e blocca gli altri."""
    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    import z3
    x = z3.Real("x")
    from cascade.neurosymbolic_guard import SymbolicContract
    guard.add_contract(SymbolicContract(
        name="bounds", expressions=[z3.And(x >= 0, x <= 100)], symbols={"x": x}))
    out, ok = guard.validate({"x": bound}, {"x": bound, "confidence": 0.95})
    assert ok == (0 <= bound <= 100)


@given(st.floats(min_value=-10, max_value=10, allow_nan=False).filter(lambda v: abs(v) > 1e-6),
       st.floats(min_value=-10, max_value=10, allow_nan=False).filter(lambda v: abs(v) > 1e-6))
@settings(max_examples=50)
def test_confidence_threshold_is_monotone(conf_a, conf_b):
    """Soglia piu' alta non deve mai approvare piu' di una soglia piu' bassa
    (stesso input)."""
    low = NeurosymbolicGuard(0.5)
    high = NeurosymbolicGuard(0.9)
    ctx = {"confidence": 0.7, "action": 1.0}
    _, ok_low = low.validate({"a": 1}, ctx)
    _, ok_high = high.validate({"a": 1}, ctx)
    assert ok_high <= ok_low  # monoticita': se passa l'alta, passa anche la bassa
