"""CASCADE - Passo 6: azione.autorizza con il Permit ActionGrant (SIX-IDE).

Destruttura i contratti v1 (contracts_v1) nella forma triangolare del Permit
che in SIX-IDE esiste gia' a tre facce (grant.rs <-> grant.ts <->
latent_brain_plus/gateway/granting.py): 13 campi, schema_version=1,
reuse="once", trusted issuance (registro), consumo one-shot NEL SET (mai
muto dello status), deep-compare dei params per forma canonica (niente hash
artigianali: confronto byte per byte della forma canonica).

Autorizzazione = percorso di cattura bianco prima dell'azione:
    1. Authorize del documento ActionGrant contro il registro (emissione
       fiduciosa, una-copia-non-vince, revoca, expiry, monouso);
    2. RICONTROLLO ATOMICO delle precondizioni del Permit al momento
       dell'uso (anti-TOCTOU: `arguments_digest` ridefinito dallo stato
       CORRENTE, scope dentro il permesso, scadenza del permit);
    3. Esecutore; l'esito e' SEMPRE un ExecutionResult tipizzato, mai
       un'eccezione: Failed (denied/precondizioni/esecutore fallito),
       Succeeded (receipt + postcondizioni osservate),
       Indeterminate (risposta persa: da riconciliare, mai Failed).

Fonte del contratto: SIX_MADRE/01_CORE_SIX_RECOVERX/RecoverX_SIX/SIX-IDE/
src-tauri/src/grant.rs (authorize) e LATENT_BRAIN_PLUS/gateway/granting.py
(parse/issue). Limite ereditato e documentato: il registro e' IN MEMORIA —
la protezione replay non sopravvive al riavvio del processo.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from .contracts import canonical_json
from .contracts_v1 import (
    Authorization,
    Deny,
    ExecutionResult,
    Failed,
    Indeterminate,
    Permit,
    Result,
    Review,
    Succeeded,
    contract_digest,
)

GRANT_SCHEMA_VERSION = 1

_GRANT_FIELDS = (
    "schema_version", "id", "tool", "scope", "principal", "session_id",
    "request_id", "operation_id", "params", "issued_at", "expires_at",
    "reuse", "status",
)


# --------------------------------------------------------------------------- #
# ActionGrant — la forma condivisa (stesso schema JSON in RUST/TS/PY)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ActionGrant:
    schema_version: int = GRANT_SCHEMA_VERSION
    id: str = ""
    tool: str = ""
    scope: str = ""
    principal: str = ""
    session_id: str = ""
    request_id: str = ""
    operation_id: str = ""
    params: dict[str, Any] = None
    issued_at: str = ""
    expires_at: str = ""
    reuse: str = "once"
    status: str = "active"

    def __post_init__(self) -> None:
        if self.params is None:
            object.__setattr__(self, "params", {})

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in _GRANT_FIELDS}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> tuple["ActionGrant", str]:
        """Validazione strutturale (come parse_action_grant di granting.py).

        NOTA (allineata a grant.rs): lo `status` NEL documento presentato non
        e' mai autoritativo — il consumo prematuro TS che segna 'used'
        sull'oggetto non deve negare un'esecuzione legittima del record. La
        verifica dello status sta nel REGISTRO, non qui.
        """
        if not isinstance(raw, Mapping):
            return None, "grant non e' un oggetto JSON"
        missing = [f for f in _GRANT_FIELDS if f not in raw]
        if missing:
            return None, f"campo mancante: {missing[0]}"
        g = cls(
            schema_version=int(raw["schema_version"]), id=str(raw["id"]),
            tool=str(raw["tool"]), scope=str(raw["scope"]),
            principal=str(raw["principal"]), session_id=str(raw["session_id"]),
            request_id=str(raw["request_id"]),
            operation_id=str(raw["operation_id"]),
            params=dict(raw["params"] or {}),
            issued_at=str(raw["issued_at"]), expires_at=str(raw["expires_at"]),
            reuse=str(raw["reuse"]), status=str(raw["status"]),
        )
        if g.schema_version != GRANT_SCHEMA_VERSION:
            return None, f"schema_version non supportato: {g.schema_version!r}"
        if g.reuse != "once":
            return None, f"reuse grant = {g.reuse!r} (atteso 'once')"
        return g, ""


def _params_eq(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Deep-compare per forma canonica: niente hash, niente ordine di chiavi."""
    return canonical_json(a) == canonical_json(b)


def grant_from_permit(
    permit: Permit,
    *,
    tool: str,
    scope: str,
    params: Mapping[str, Any],
    principal: str = "cascade",
    session_id: str = "session:cascade",
    request_id: str | None = None,
    operation_id: str | None = None,
    ttl_seconds: int = 600,
) -> ActionGrant:
    """Destrutturazione: Authorization (Permit v1) -> documento ActionGrant.

    L'id e' il grant_id anti-riuso del permit; params sono gli argomenti
    dell'azione (deep-compare alla verifica). La data di scadenza viene dal
    permit stesso e dal TTL.
    """
    now = datetime.now(timezone.utc)
    expiry = now.timestamp() + max(0, int(ttl_seconds))
    expires = datetime.fromtimestamp(expiry, tz=timezone.utc)
    return ActionGrant(
        id=permit.grant_id,
        tool=tool, scope=scope,
        principal=principal, session_id=session_id,
        request_id=request_id or uuid.uuid4().hex,
        operation_id=operation_id or uuid.uuid4().hex,
        params=dict(params),
        issued_at=now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        expires_at=expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        reuse="once", status="active",
    )


# --------------------------------------------------------------------------- #
# GrantRegistry — trusted issuance e authorize a una via
# --------------------------------------------------------------------------- #


class GrantRegistry:
    """Registro di emissione fiduciosa + consumo monouso (in memoria).

    Coerente con grant.rs: `authorize` non si fida del documento — l'autorita'
    sta nel RECORD REGISTRATO. Il consumo vive nel set `consumed`, non in una
    mutazione di status (il consumo prematuro TS non nega esecuzioni legittime).
    """

    def __init__(self):
        self._issued: dict[str, ActionGrant] = {}
        self._consumed: set[str] = set()

    def issue(self, grant: ActionGrant) -> Result[ActionGrant, str]:
        g, err = ActionGrant.from_dict(grant.to_dict())
        if err:
            return Result.err(err)
        if g.id in self._issued:
            return Result.err("DENIED: grant_used: grant gia' registrato")
        if not g.id:
            return Result.err("DENIED: grant_invalid: id vuoto")
        self._issued[g.id] = g
        return Result.ok(g)

    def revoke(self, grant_id: str) -> bool:
        rec = self._issued.get(grant_id)
        if rec is None:
            return False
        self._issued[grant_id] = ActionGrant(**{**rec.to_dict(), "status": "revoked"})
        return True

    def authorize(self, raw: Any, *, tool: str, scope: str,
                  params: Mapping[str, Any],
                  now: float | None = None) -> Result[ActionGrant, str]:
        g, err = ActionGrant.from_dict(raw)
        if err:
            return Result.err(f"DENIED ({tool}): grant_invalid: {err}")

        granted = self._issued.get(g.id)
        if granted is None:
            return Result.err(
                f"DENIED ({tool}): grant_not_issued: nessun record per id={g.id}")
        if granted.status != "active":
            return Result.err(f"DENIED ({tool}): grant_revoked: status {granted.status}")

        # La copia non vince mai: ogni campo autorevole deve combaciare col record.
        for field in ("id", "tool", "scope", "principal", "session_id",
                      "request_id", "operation_id", "reuse", "expires_at"):
            if getattr(granted, field) != getattr(g, field):
                return Result.err(
                    f"DENIED ({tool}): grant_registry_mismatch: {field} divergente")

        if granted.tool != tool:
            return Result.err(f"DENIED ({tool}): tool_mismatch")
        if granted.scope != scope:
            return Result.err(f"DENIED ({tool}): scope_mismatch")
        if not _params_eq(granted.params, params):
            return Result.err(f"DENIED ({tool}): params_mismatch")

        now = time.time() if now is None else float(now)
        try:
            expires = datetime.fromisoformat(
                granted.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return Result.err(f"DENIED ({tool}): grant_invalid: expires_at non RFC3339")
        if expires.timestamp() < now:
            return Result.err(f"DENIED ({tool}): grant_expired")

        if g.id in self._consumed:
            return Result.err(f"DENIED ({tool}): grant_used: monouso")
        self._consumed.add(g.id)
        return Result.ok(granted)

    def reset(self) -> None:
        self._issued.clear()
        self._consumed.clear()


# --------------------------------------------------------------------------- #
# Ricontrollo atomico delle precondizioni (anti-TOCTOU) — passo 2 + 6
# --------------------------------------------------------------------------- #


def recheck_preconditions(
    permit: Permit,
    *,
    args_digest_now: str,
    scope_now: Iterable[str],
    now: float | None = None,
) -> Result[bool, str]:
    """Le condizioni al MOMENTO DELL'USO devono ancora reggere.

    `args_digest_now` e' la digest degli argomenti CHE STIAMO PER PASSARE,
    ridefinita dallo stato corrente (non da cio' che era stato autorizzato):
    se il mondo e' cambiato tra emissione e azione, il risultato e' errore.
    """
    t = time.time() if now is None else float(now)
    if permit.expires_at < t:
        return Result.err("DENIED: preconditions: permit scaduto al momento dell'uso")
    if permit.arguments_digest != args_digest_now:
        return Result.err(
            "DENIED: preconditions: argomenti cambiati dopo l'autorizzazione (TOCTOU)")
    if not set(scope_now) <= set(permit.scope):
        return Result.err("DENIED: preconditions: scope fuori dal permesso")
    return Result.ok(True)


# --------------------------------------------------------------------------- #
# azione.autorizza — la cattura bianca prima dell'esecuzione
# --------------------------------------------------------------------------- #


def azione_autorizza(
    registry: GrantRegistry,
    permit: Authorization,
    grant_doc: Any,
    *,
    tool: str,
    scope: str,
    params: Mapping[str, Any],
    state: Mapping[str, Any],
    executor: Callable[[dict[str, Any]], Any] | None = None,
    timeout_ms: int | None = None,
) -> ExecutionResult:
    """Autorizza e (se tutto regge) esegue. Mai un'eccezione come esito.

    Order: Permit != Deny/Review -> authorize(ActionGrant) -> recheck atomico
    -> executor. Qualunque passo fallisce => Failed tipizzato e l'esecutore
    NON viene toccato. Esecutore assente o con timeout perso => Indeterminate
    (da riconciliare, mai un Failed simulato).
    """
    if isinstance(permit, Deny):
        return Failed(f"denied: {permit.reason}")
    if isinstance(permit, Review):
        return Failed(f"review: {permit.reason}")

    auth = registry.authorize(grant_doc, tool=tool, scope=scope, params=params)
    if auth.is_err:
        return Failed(auth.error)

    args_digest_now = contract_digest(**dict(sorted(state.items())))
    pre = recheck_preconditions(permit, args_digest_now=args_digest_now,
                                scope_now=(scope,))
    if pre.is_err:
        return Failed(pre.error)

    if executor is None:
        return Indeterminate(f"reconcile:executor:{auth.value.id}")

    if timeout_ms is not None and timeout_ms > 0:
        # Tempo VERO sull'esecutore: passato il limite la risposta e' persa
        # (l'azione potrebbe essere avvenuta) -> Indeterminate da riconciliare.
        box: dict[str, Any] = {}

        def _run() -> None:
            try:
                box["out"] = executor(dict(params))
            except BaseException as exc:  # noqa: BLE001
                box["exc"] = exc

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(float(timeout_ms) / 1000.0)
        if t.is_alive():
            return Indeterminate(f"reconcile:timeout:{auth.value.id}")
        if "exc" in box:
            exc = box["exc"]
            if isinstance(exc, TimeoutError):
                return Indeterminate(f"reconcile:timeout:{auth.value.id}")
            return Failed(f"{type(exc).__name__}: {exc}")
        out = box.get("out")
    else:
        try:
            out = executor(dict(params))
        except TimeoutError:
            # risposta persa dopo che l'azione POTREBBE essere avvenuta
            return Indeterminate(f"reconcile:timeout:{auth.value.id}")
        except Exception as exc:  # noqa: BLE001
            return Failed(f"{type(exc).__name__}: {exc}")

    if isinstance(out, dict) and out.get("ok") is False:
        return Failed(str(out.get("error", "fallimento esecutore")))
    return Succeeded(
        receipt=f"{tool}:{scope}:{auth.value.id}",
        observed_postconditions=tuple(sorted(state)),
    )