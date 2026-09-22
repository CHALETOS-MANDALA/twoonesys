"""Ricevuta firmata di un'azione autorizzata o negata.

Verificabile da chi ha solo il materiale pubblico (chiave + registry).
Schema: cascade.receipt.v1
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .contracts import canonical_json
from . import signing
from .signing import KeyRegistry, SigningIdentity

RECEIPT_SCHEMA = "cascade.receipt.v1"
CONTRACT_DIGEST = "cascade-fs-write-sandbox-v1"


@dataclass
class ActionReceipt:
    schema: str
    request_id: str
    policy: str
    tool: str
    scope: str
    principal: str
    authorized: bool
    outcome: bool | None
    deny_reason: str
    evidence_ref: str
    solver_status: str
    path: str
    created_at: float
    key_id: str
    signature: str
    contract_digest: str

    def payload(self) -> bytes:
        data = asdict(self)
        data.pop("signature", None)
        return canonical_json(data)

    def sign_with(self, identity: SigningIdentity) -> "ActionReceipt":
        self.key_id = identity.key_id
        self.signature = identity.sign(self.payload()).hex()
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8")
        return target

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ActionReceipt":
        return cls(
            schema=str(raw.get("schema", "")),
            request_id=str(raw.get("request_id", "")),
            policy=str(raw.get("policy", "")),
            tool=str(raw.get("tool", "")),
            scope=str(raw.get("scope", "")),
            principal=str(raw.get("principal", "")),
            authorized=bool(raw.get("authorized")),
            outcome=raw.get("outcome"),
            deny_reason=str(raw.get("deny_reason", "")),
            evidence_ref=str(raw.get("evidence_ref", "")),
            solver_status=str(raw.get("solver_status", "")),
            path=str(raw.get("path", "")),
            created_at=float(raw.get("created_at") or 0.0),
            key_id=str(raw.get("key_id", "")),
            signature=str(raw.get("signature", "")),
            contract_digest=str(raw.get("contract_digest", "")),
        )

    @classmethod
    def load(cls, path: str | Path) -> "ActionReceipt":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def issue_receipt(
    *,
    request_id: str,
    policy: str,
    tool: str,
    scope: str,
    authorized: bool,
    outcome: bool | None,
    path: str,
    deny_reason: str = "",
    evidence_ref: str = "",
    solver_status: str = "",
    principal: str = "cascade",
    identity: SigningIdentity | None = None,
    registry: KeyRegistry | None = None,
) -> ActionReceipt:
    ident = identity or SigningIdentity.load_or_create()
    rec = ActionReceipt(
        schema=RECEIPT_SCHEMA,
        request_id=request_id,
        policy=policy,
        tool=tool,
        scope=scope,
        principal=principal,
        authorized=authorized,
        outcome=outcome,
        deny_reason=deny_reason,
        evidence_ref=evidence_ref,
        solver_status=solver_status or ("rules_verified" if authorized else "denied"),
        path=str(path),
        created_at=time.time(),
        key_id="",
        signature="",
        contract_digest=CONTRACT_DIGEST,
    ).sign_with(ident)
    if registry is not None:
        registry.register(ident)
    return rec


def verify_receipt(
    receipt: ActionReceipt | str | Path | Mapping[str, Any],
    registry: KeyRegistry | None = None,
) -> tuple[bool, str]:
    """Verifica con il solo materiale pubblico. Chiave sconosciuta = no."""
    if isinstance(receipt, (str, Path)):
        rec = ActionReceipt.load(receipt)
    elif isinstance(receipt, ActionReceipt):
        rec = receipt
    else:
        rec = ActionReceipt.from_dict(receipt)
    if rec.schema != RECEIPT_SCHEMA:
        return False, f"schema non supportato: {rec.schema!r}"
    if not rec.signature or not rec.key_id:
        return False, "ricevuta senza firma o key_id"
    keys = registry if registry is not None else KeyRegistry(signing.DEFAULT_PUBLIC_KEYS)
    if not rec.key_id:
        return False, "key_id assente"
    if keys.public_for(rec.key_id) is None:
        return False, "chiave sconosciuta: non verificabile"
    if not keys.verify(rec.key_id, rec.payload(), bytes.fromhex(rec.signature)):
        return False, "firma non valida o chiave sconosciuta"
    return True, (
        f"ok request_id={rec.request_id} authorized={rec.authorized} "
        f"outcome={rec.outcome} policy={rec.policy} key_id={rec.key_id}"
    )
