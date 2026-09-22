"""Test della Guardia Neurosymbolic (Layer 5)."""

import z3
import pytest

from cascade.neurosymbolic_guard import (
    ConfidenceLevel,
    NeurosymbolicGuard,
    SymbolicContract,
    medical_guard,
)


def test_pass_high_confidence():
    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    out, ok = guard.validate({"x": 1}, {"confidence": 0.95})
    assert ok
    assert out == {"x": 1}


def test_fail_low_confidence():
    guard = NeurosymbolicGuard(ConfidenceLevel.CRITICAL)
    out, ok = guard.validate({"x": 1}, {"confidence": 0.5})
    assert not ok
    assert out is None


def test_contract_bounds_violation():
    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    guard.add_int_bounds("dosaggio", 0, 500)
    out, ok = guard.validate({"dose": 600}, {"dosaggio": 600, "confidence": 0.95,
                                             "safe_fallback": {"dose": 500}})
    assert not ok
    assert out == {"dose": 500}


def test_contract_bounds_ok():
    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    guard.add_int_bounds("dosaggio", 0, 500)
    out, ok = guard.validate({"dose": 300}, {"dosaggio": 300, "confidence": 0.95})
    assert ok


def test_block_on_no_fallback():
    guard = NeurosymbolicGuard(ConfidenceLevel.GENERAL)
    guard.add_int_bounds("dosaggio", 0, 100)
    out, ok = guard.validate({"dose": 500}, {"dosaggio": 500, "confidence": 0.95})
    assert not ok
    assert out is None


def test_medical_guard_ok():
    guard = medical_guard()
    ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
           "allergia": False, "somministra": True, "confidence": 1.0}
    out, ok = guard.validate({"dose": 400}, ctx)
    assert ok


def test_medical_guard_allergy_blocks():
    guard = medical_guard()
    ctx = {"dosaggio": 400.0, "dosaggio_max": 500.0,
           "allergia": True, "somministra": True, "confidence": 1.0}
    out, ok = guard.validate({"dose": 400}, ctx)
    assert not ok
    assert out is None


def test_violations_logged():
    guard = NeurosymbolicGuard(ConfidenceLevel.CRITICAL)
    guard.validate({"x": 1}, {"confidence": 0.1})
    guard.validate({"x": 1}, {"confidence": 0.2})
    assert guard.incident_count == 2
    assert len(guard.violations) == 2
