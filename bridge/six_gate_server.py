"""TWOONESYS Gate — faccia HTTP per SIX-IDE.

Rizzo misura (tipo + probabilita', 0 token). CASCADE decide se quella
misura puo' toccare il mondo e firma la ricevuta. Il gate non esegue.

Porta canonica: 8018 (ports.yaml: twoonesys_gate).
Se :8017 e' spento: mode=soft passa al control-plane locale; mode=strict nega.

    python bridge/six_gate_server.py
    oppure: bridge\\AVVIA_GATE.bat
"""

from __future__ import annotations

import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "bridge"))
sys.path.insert(0, str(ROOT / "pct"))
sys.path.insert(0, str(ROOT))

from cascade.rizzo_bridge import RizzoBridgeError, RizzoProposer  # noqa: E402
from cascade.receipt import issue_receipt  # noqa: E402
from cascade.guarded import path_in_sandbox, sandbox_root  # noqa: E402
from detector_contract import (  # noqa: E402
    StructuralFacts,
    label_from_score,
    structural_score,
    textual_score,
)
from run7_eval import T_from_soft  # noqa: E402
from episode_contract import Episode, SCALA_TWOONESYS  # noqa: E402

ENGINE = "http://127.0.0.1:8017"
PORT = 8018
T_PRESENT, T_ABSENT = 0.01, 100.0
EPISODES = ROOT / "bridge" / "run_six" / "episodes.jsonl"
RECEIPTS = ROOT / "bridge" / "run_six" / "receipts"
WRITE_TOOLS = {
    "write_file", "file_write", "file_edit", "file_delete",
    "create_folder", "file_mkdir", "file_copy", "file_move",
}

app = FastAPI(title="TWOONESYS Gate", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
_proposer: RizzoProposer | None = None


def proposer() -> RizzoProposer:
    global _proposer
    if _proposer is None:
        _proposer = RizzoProposer(base_url=ENGINE, timeout=60.0)
    return _proposer


def calibrate(raw: float, score: float) -> float:
    p = min(max(raw, 1e-6), 1 - 1e-6)
    logit = math.log(p / (1 - p))
    T = max(T_from_soft(score, T_PRESENT, T_ABSENT), 1e-3)
    x = max(min(logit / T, 60.0), -60.0)
    ex = math.exp(x)
    return ex / (ex + 1.0)


def textual_for(text: str) -> float:
    s = textual_score(text.lower(), "screenshot", ["fattura", "bug"])
    low = text.lower()
    if any(w in low for w in ("screenshot", "verificat", "prova", "attached", "allegat")):
        s += 1.0
    return s


def _tool_path(params: dict[str, Any]) -> str:
    for k in ("path", "file_path", "target", "dst", "src"):
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def cascade_stamp(
    *,
    gate_id: str,
    tool: str,
    params: dict[str, Any],
    authorized: bool,
    rizzo_decision: str | None,
    deny_reason: str = "",
) -> tuple[bool, dict[str, Any]]:
    """Dopo Rizzo: CASCADE autorizza o nega, e firma. Non esegue.

    Se CASCADE_SANDBOX e' impostato e il tool scrive, il path deve stare
    nel sandbox — anche se Rizzo ha detto allow. Senza sandbox, la ricevuta
    resta la prova; il confine dei path e' il Control Plane di SIX.
    """
    path = _tool_path(params)
    auth = authorized
    deny = deny_reason
    policy = "twoonesys.effect.v1"
    sandbox_on = bool(os.environ.get("CASCADE_SANDBOX"))
    if auth and tool in WRITE_TOOLS and path and sandbox_on:
        if not path_in_sandbox(path):
            auth = False
            deny = f"CASCADE: path fuori sandbox ({sandbox_root()})"
            policy = "fs.write.sandbox"
    try:
        rec = issue_receipt(
            request_id=gate_id,
            policy=policy,
            tool=tool,
            scope="sandbox" if sandbox_on else "six-effect",
            authorized=auth,
            outcome=None,
            path=path,
            deny_reason=deny,
            evidence_ref=f"rizzo:{rizzo_decision or 'none'}",
            solver_status="rules_verified" if auth else "denied",
            principal="twoonesys.gate",
        )
        RECEIPTS.mkdir(parents=True, exist_ok=True)
        rec.save(RECEIPTS / f"{gate_id}.json")
        return auth, rec.to_dict()
    except Exception as exc:  # noqa: BLE001
        return auth, {"error": f"CASCADE receipt fallita: {exc}", "authorized": auth}


class FactsIn(BaseModel):
    n: int = 0
    kernel_available: bool = True
    kernel_value_attached: bool = False
    kernel_value: str | None = None
    verdict_ok: bool | None = None
    verdict_code: str | None = None
    engine_status: str = ""
    provenance_ok: bool = True
    evidence_stale: bool = False
    evidence_incomplete: bool = False
    sources_conflict: bool = False
    component_unreachable: bool = False


class EffectReq(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    user_text: str = ""
    mode: str = "soft"  # soft | strict
    facts: FactsIn | None = None
    ledger_evidenza: bool | None = None


class TriageReq(BaseModel):
    ticket: str
    ledger_evidenza: bool | None = None
    facts: FactsIn | None = None


class EpisodeReq(BaseModel):
    request_id: str | None = None
    tool: str = ""
    authorized: bool = False
    outcome_ok: bool = False
    outcome_code: str = "UNKNOWN_STATE"
    ledger_evidenza: bool | None = None
    raw_confidence: float | None = None
    reparto_scelto: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def facts_from(req_facts: FactsIn | None, ledger: bool | None) -> StructuralFacts:
    if req_facts is not None:
        d = req_facts.model_dump()
        # engine_status must match Literal
        return StructuralFacts.from_dict(d)
    if ledger is True:
        return StructuralFacts(
            n=1, kernel_value_attached=True,
            kernel_value="ledger:verified:six",
            verdict_ok=True, verdict_code="ledger_match", engine_status="ok")
    if ledger is False:
        return StructuralFacts(
            n=0, kernel_value_attached=False,
            engine_status="insufficient_evidence")
    return StructuralFacts(n=0, engine_status="unknown", evidence_incomplete=True)


EFFECT_Q = {
    "effect": {
        "type": "choice",
        "instructions": (
            "Questa azione ha effetto sul mondo (file/terminale/rete). "
            "Concedi solo se e' sicura e giustificata dal contesto. "
            "allow = procedere; deny = bloccare."
        ),
        "options": [
            {"id": "allow", "description": "Azione giustificata e sicura: autorizzare"},
            {"id": "deny", "description": "Rischio, evidenza insufficiente o azione sproporzionata: negare"},
        ],
        "policy": {"allow_abstain": False},
    },
}

TRIAGE_Q = {
    "reparto": {
        "type": "choice",
        "instructions": "Quale reparto deve gestire questo ticket?",
        "options": [
            {"id": "billing", "description": "Pagamenti, fatture, rimborsi"},
            {"id": "technical", "description": "Bug, malfunzionamenti, outage"},
            {"id": "sales", "description": "Vendite, preventivi, contratti"},
        ],
        "policy": {"allow_abstain": False},
    },
}


def _pack(
    body: dict[str, Any],
    *,
    tool: str,
    params: dict[str, Any],
    gate_id: str,
) -> dict[str, Any]:
    auth, cascade = cascade_stamp(
        gate_id=gate_id,
        tool=tool,
        params=params,
        authorized=bool(body.get("authorized")),
        rizzo_decision=body.get("decision") if isinstance(body.get("decision"), str) else None,
        deny_reason="" if body.get("authorized") else str(body.get("reason") or ""),
    )
    body["authorized"] = auth
    if not auth and cascade.get("deny_reason") and "CASCADE:" in str(cascade.get("deny_reason")):
        body["decision"] = "deny"
        body["reason"] = cascade["deny_reason"]
    body["cascade"] = cascade
    return body


@app.get("/health")
def health() -> dict[str, Any]:
    eng: dict[str, Any] = {"status": "down"}
    try:
        eng = proposer().health()
    except Exception as exc:  # noqa: BLE001
        eng = {"status": "down", "error": str(exc)[:200]}
    return {
        "status": "ready",
        "service": "twoonesys_gate",
        "port": PORT,
        "engine": eng,
        "engine_url": ENGINE,
        "contract": "twoonesys-six-gate-v1",
        "cascade": "receipt+policy",
    }


@app.post("/v1/effect/authorize")
def authorize_effect(body: EffectReq) -> dict[str, Any]:
    gate_id = str(uuid.uuid4()).replace("-", "")
    facts = facts_from(body.facts, body.ledger_evidenza)
    s_s = structural_score(facts)
    lab = label_from_score(s_s)
    text = body.user_text or f"{body.tool} {json.dumps(body.params, ensure_ascii=False)[:400]}"
    s_t = textual_for(text)
    kw = {"tool": body.tool, "params": body.params, "gate_id": gate_id}

    # Hard deny strutturale — indipendente dall'engine
    if facts.component_unreachable or facts.sources_conflict or facts.evidence_stale:
        return _pack({
            "gate_id": gate_id,
            "authorized": False,
            "engine_available": False,
            "raw_confidence": None,
            "decision": "deny",
            "m4_textual": None,
            "m4_structural": calibrate(0.99, s_s) if s_s else 0.5,
            "s_textual": s_t,
            "s_structural": s_s,
            "label_structural": lab,
            "reason": "deny strutturale (stale/conflict/unreachable) — senza engine",
            "touched": datetime.now(timezone.utc).isoformat(),
        }, **kw)

    try:
        prop = proposer().propose(
            {
                "tool": body.tool,
                "params": {k: str(v)[:200] for k, v in list(body.params.items())[:12]},
                "user_text": body.user_text[:1500],
                "structural_usable": lab,
            },
            EFFECT_Q,
            question="effect",
        )
    except RizzoBridgeError as exc:
        if body.mode == "strict":
            return _pack({
                "gate_id": gate_id,
                "authorized": False,
                "engine_available": False,
                "raw_confidence": None,
                "decision": None,
                "m4_textual": None,
                "m4_structural": None,
                "s_textual": s_t,
                "s_structural": s_s,
                "label_structural": lab,
                "reason": f"engine down (strict): {exc}",
                "touched": datetime.now(timezone.utc).isoformat(),
            }, **kw)
        return _pack({
            "gate_id": gate_id,
            "authorized": True,
            "engine_available": False,
            "raw_confidence": None,
            "decision": None,
            "m4_textual": None,
            "m4_structural": None,
            "s_textual": s_t,
            "s_structural": s_s,
            "label_structural": lab,
            "reason": f"engine down (soft): control-plane locale — {exc}",
            "touched": datetime.now(timezone.utc).isoformat(),
        }, **kw)

    raw = float(prop.confidence)
    m4_t = calibrate(raw, s_t)
    m4_s = calibrate(raw, s_s)
    decision = prop.value or "deny"
    authorized = decision == "allow"
    if prop.abstained:
        authorized = False
        decision = "deny"

    return _pack({
        "gate_id": gate_id,
        "authorized": authorized,
        "engine_available": True,
        "raw_confidence": raw,
        "decision": decision,
        "m4_textual": m4_t,
        "m4_structural": m4_s,
        "s_textual": s_t,
        "s_structural": s_s,
        "label_structural": lab,
        "reason": (
            f"engine={decision} raw={raw:.4f} m4_s={m4_s:.4f} m4_t={m4_t:.4f}"
        ),
        "model_id": prop.model_id,
        "touched": datetime.now(timezone.utc).isoformat(),
    }, **kw)


@app.post("/v1/triage")
def triage(body: TriageReq) -> dict[str, Any]:
    if not body.ticket.strip():
        raise HTTPException(400, "ticket vuoto")
    facts = facts_from(body.facts, body.ledger_evidenza)
    s_s = structural_score(facts)
    s_t = textual_for(body.ticket)
    try:
        prop = proposer().propose(
            {"ticket": body.ticket, "ref": "six-triage"},
            TRIAGE_Q,
            question="reparto",
        )
    except RizzoBridgeError as exc:
        raise HTTPException(503, f"engine down: {exc}") from exc
    raw = float(prop.confidence)
    m4_t = calibrate(raw, s_t)
    m4_s = calibrate(raw, s_s)
    return {
        "reparto": prop.value,
        "raw_confidence": raw,
        "m4_textual": m4_t,
        "m4_structural": m4_s,
        "s_textual": s_t,
        "s_structural": s_s,
        "divergence": abs(m4_t - m4_s) > 0.05,
        "ledger_evidenza": body.ledger_evidenza,
        "model_id": prop.model_id,
        "touched": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/episode")
def episode(body: EpisodeReq) -> dict[str, Any]:
    rid = body.request_id or f"six-{uuid.uuid4().hex[:12]}"
    ep = Episode(request_id=rid)
    ep.set_condition(
        ledger_evidenza=body.ledger_evidenza,
        ref_ordine=rid,
        ticket_text_hash=rid[:16],
    )
    ep.set_action(
        reparto_scelto=body.reparto_scelto or body.tool or "unknown",
        raw_confidence=body.raw_confidence,
        selection_probability=float(body.raw_confidence or 0.0),
    )
    ep.set_executed(authorized=body.authorized, tool=body.tool)
    code = body.outcome_code
    if code not in SCALA_TWOONESYS.valori:
        code = "UNKNOWN_STATE"
    ep.set_outcome(code, outcome_ok=body.outcome_ok, **body.extra)
    rec = ep.to_record()
    EPISODES.parent.mkdir(parents=True, exist_ok=True)
    with EPISODES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "request_id": rid,
        "outcome_contract": rec.get("outcome_contract"),
        "outcome_magnitude": rec.get("outcome_magnitude"),
        "path": str(EPISODES),
    }


def main() -> None:
    print(f"TWOONESYS Gate su :{PORT}  (engine {ENGINE})")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
