"""Test del protocollo A2A (Layer 4)."""

import pytest

from cascade.a2a_protocol import (
    AgentManifest,
    AgentRegistry,
    TaskRequest,
    generate_keypair,
    negotiate,
    sign_payload,
    verify_payload,
)


def test_sign_verify_roundtrip():
    priv, pub = generate_keypair()
    obj = {"a": 1, "b": "x"}
    sig = sign_payload(priv, obj)
    assert verify_payload(pub, obj, sig)
    assert not verify_payload(pub, {**obj, "a": 2}, sig)


def test_signature_rejects_wrong_key():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    obj = {"a": 1}
    sig = sign_payload(priv_a, obj)
    assert not verify_payload(pub_b, obj, sig)


def test_registry_discover():
    reg = AgentRegistry()
    _, pub = generate_keypair()
    reg.register(AgentManifest("alice", pub, ["vision", "nlp"], 2.0, 0.9))
    assert [a.agent_id for a in reg.discover("vision")] == ["alice"]
    assert reg.discover("audio") == []


def test_registry_discover_cost_filter():
    reg = AgentRegistry()
    _, pub = generate_keypair()
    reg.register(AgentManifest("bob", pub, ["vision"], 20.0, 0.8))
    assert reg.discover("vision", max_cost=10.0) == []


def test_negotiate_assigns_capable():
    reg = AgentRegistry()
    _, pub = generate_keypair()
    reg.register(AgentManifest("carol", pub, ["vision"], 3.0, 0.5))
    req = TaskRequest("t1", "vision", {}, max_cost=5.0, requester_id="me")
    res = negotiate(reg, req)
    assert res.accepted
    assert res.agent_id == "carol"


def test_negotiate_rejects_if_no_capable():
    reg = AgentRegistry()
    _, pub = generate_keypair()
    reg.register(AgentManifest("dave", pub, ["nlp"], 1.0, 0.5))
    req = TaskRequest("t2", "vision", {}, max_cost=5.0, requester_id="me")
    res = negotiate(reg, req)
    assert not res.accepted


def test_reputation_tracks():
    reg = AgentRegistry()
    _, pub = generate_keypair()
    reg.register(AgentManifest("eve", pub, ["nlp"], 1.0, 0.5))
    r1 = reg.reputation("eve")
    r2 = reg.report_outcome("eve", 1.0, alpha=0.5)
    assert r2 > r1
