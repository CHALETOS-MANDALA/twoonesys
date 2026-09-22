"""API vendibile: @guarded(policy=...) su un'azione che tocca il mondo.

Policy:
- fs.write.sandbox — scrive solo un path dentro CASCADE_SANDBOX
- exec.sandbox — avvia solo un programma il cui file è già dentro il sandbox
  (niente shell, niente PATH). Non legge il corpo dello script.

L'azione non parte senza un Permit + grant anti-TOCTOU. In ogni caso
(eseguita o bloccata) esce una ricevuta firmata.
"""

from __future__ import annotations

import inspect
import os
import sys
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from .action_authorize import GrantRegistry, azione_autorizza, grant_from_permit
from .contracts_v1 import Permit, Succeeded, contract_digest
from .receipt import ActionReceipt, issue_receipt
from .signing import KeyRegistry, SigningIdentity

POLICY_FS_WRITE = "fs.write.sandbox"
POLICY_EXEC = "exec.sandbox"
POLICIES = frozenset({POLICY_FS_WRITE, POLICY_EXEC})
DEFAULT_SANDBOX_ENV = "CASCADE_SANDBOX"


class ActionDenied(RuntimeError):
    """L'azione non aveva il diritto di partire. Porta la ricevuta."""

    def __init__(self, receipt: ActionReceipt):
        super().__init__(receipt.deny_reason or "azione negata")
        self.receipt = receipt


def sandbox_root() -> Path:
    raw = os.environ.get(DEFAULT_SANDBOX_ENV)
    if raw:
        return Path(raw).resolve()
    return (Path.cwd() / "cascade_sandbox").resolve()


def path_in_sandbox(path: str | Path, root: Path | None = None) -> bool:
    root = (root or sandbox_root()).resolve()
    try:
        Path(path).resolve().relative_to(root)
        return True
    except ValueError:
        return False


def default_key_registry() -> KeyRegistry:
    from .signing import DEFAULT_PUBLIC_KEYS
    return KeyRegistry(DEFAULT_PUBLIC_KEYS)


def _write_params(fn: Callable[..., Any], args: tuple, kwargs: dict) -> dict[str, Any]:
    bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    bound.apply_defaults()
    data = dict(bound.arguments)
    path = data.get("path") or data.get("target")
    if path is None and args:
        path = args[0]
    return {"path": str(path) if path is not None else ""}


def _exec_target(fn: Callable[..., Any], args: tuple, kwargs: dict) -> tuple[str, str, str]:
    """(script, cwd, errore). Vuoto errore = può partire.

    Unico avvio ammesso: l'interprete di questo processo + un solo file .py
    che sta già nel sandbox. Niente shell, niente PATH, niente -c.
    """
    bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    bound.apply_defaults()
    data = dict(bound.arguments)
    argv = data.get("argv")
    cwd = data.get("cwd")
    if argv is None and args:
        argv = args[0]
    if cwd is None and len(args) > 1:
        cwd = args[1]
    if not isinstance(argv, (list, tuple)) or len(argv) != 2:
        return "", str(cwd or ""), "argv deve essere [interprete, script]"
    try:
        interp = Path(str(argv[0])).resolve()
        cwd_path = Path(str(cwd)).resolve() if cwd else sandbox_root()
        script = Path(str(argv[1]))
        script = script.resolve() if script.is_absolute() else (cwd_path / script).resolve()
    except OSError:
        return "", str(cwd or ""), "path non risolvibile"
    if interp != Path(sys.executable).resolve():
        return str(script), str(cwd_path), "interprete non ammesso"
    if not path_in_sandbox(cwd_path):
        return str(script), str(cwd_path), "cwd fuori dal sandbox"
    if script.suffix.lower() != ".py" or not path_in_sandbox(script):
        return str(script), str(cwd_path), "script fuori dal sandbox"
    if not script.is_file():
        return str(script), str(cwd_path), "script assente nel sandbox"
    return str(script), str(cwd_path), ""


def _deny(*, request_id: str, policy: str, path: str, reason: str,
          identity: SigningIdentity, keys: KeyRegistry,
          receipt_dir: Path | None, tool: str = "fs.write") -> ActionReceipt:
    rec = issue_receipt(
        request_id=request_id, policy=policy, tool=tool,
        scope="sandbox", authorized=False, outcome=False,
        path=path, deny_reason=reason, solver_status="denied",
        identity=identity, registry=keys)
    if receipt_dir is not None:
        rec.save(receipt_dir / f"{request_id}.json")
    return rec


def guarded(policy: str = POLICY_FS_WRITE, *,
            identity: SigningIdentity | None = None,
            registry: KeyRegistry | None = None,
            receipt_dir: str | Path | None = None):
    """Decorator: esegue solo se la policy autorizza; restituisce la ricevuta."""

    if policy not in POLICIES:
        raise ValueError(f"policy non supportata: {policy!r}")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> ActionReceipt:
            request_id = uuid.uuid4().hex
            ident = identity or SigningIdentity.load_or_create()
            keys = registry or default_key_registry()
            keys.register(ident)
            out_dir = Path(receipt_dir) if receipt_dir is not None else None
            tool = "fs.write" if policy == POLICY_FS_WRITE else "exec"

            if policy == POLICY_EXEC:
                path, _cwd, reason = _exec_target(fn, args, kwargs)
            else:
                path = _write_params(fn, args, kwargs)["path"]
                reason = "" if path and path_in_sandbox(path) else "path fuori dal sandbox o assente"

            if reason:
                rec = _deny(
                    request_id=request_id, policy=policy, path=path,
                    reason=reason, tool=tool,
                    identity=ident, keys=keys, receipt_dir=out_dir)
                raise ActionDenied(rec)

            state = {"path": path, "policy": policy}
            digest = contract_digest(**state)
            permit = Permit(
                action_digest=digest,
                arguments_digest=digest,
                scope=("sandbox",),
                preconditions=("path_in_sandbox",),
                expires_at=time.time() + 60,
                grant_id=uuid.uuid4().hex,
                subject_id="cascade.guarded",
            )
            grant = grant_from_permit(
                permit, tool=tool, scope="sandbox",
                params={"path": path}, request_id=request_id)
            grants = GrantRegistry()
            issued = grants.issue(grant)
            if issued.is_err:
                rec = _deny(
                    request_id=request_id, policy=policy, path=path,
                    reason=str(issued.error), tool=tool,
                    identity=ident, keys=keys, receipt_dir=out_dir)
                raise ActionDenied(rec)

            def executor(_p: dict[str, Any]) -> Any:
                return fn(*args, **kwargs)

            result = azione_autorizza(
                grants, permit, grant.to_dict(),
                tool=tool, scope="sandbox",
                params={"path": path}, state=state, executor=executor)

            if not isinstance(result, Succeeded):
                rec = _deny(
                    request_id=request_id, policy=policy, path=path,
                    reason=str(result), tool=tool,
                    identity=ident, keys=keys, receipt_dir=out_dir)
                raise ActionDenied(rec)

            observed = True if policy == POLICY_EXEC else Path(path).is_file()
            rec = issue_receipt(
                request_id=request_id, policy=policy, tool=tool,
                scope="sandbox", authorized=True, outcome=observed,
                path=path, evidence_ref=digest,
                solver_status="rules_verified",
                identity=ident, registry=keys)
            if out_dir is not None:
                rec.save(out_dir / f"{request_id}.json")
            wrapped.last_receipt = rec  # type: ignore[attr-defined]
            return rec

        wrapped.last_receipt = None  # type: ignore[attr-defined]
        return wrapped

    return decorator
