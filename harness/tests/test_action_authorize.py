"""CASCADE - Passo 6: azione.autorizza con il Permit ActionGrant.

CorrectnessSuite: i controlli del registro come in grant.rs (trusted
issuance, monouso nel set non nello status, la copia non vince, expiry,
revoca) + il ricontrollo atomico anti-TOCTOU + gli esiti tipizzati.
CompatibilitySuite: la forma condivisa del Permit (13 campi identici a
grant.ts/grant.rs/granting.py) e la destrutturazione da contracts_v1.
"""

import time

import pytest

from cascade.action_authorize import (
    GRANT_SCHEMA_VERSION,
    ActionGrant,
    GrantRegistry,
    azione_autorizza,
    grant_from_permit,
    recheck_preconditions,
)
from cascade.contracts_v1 import (
    Failed,
    Indeterminate,
    Permit,
    Succeeded,
    contract_digest,
)


def _permit(path: str = "a", expiry: float | None = None,
            grant_id: str = "grant-permit-1") -> Permit:
    return Permit(
        action_digest=contract_digest(action="file_write", scope="fs.write"),
        arguments_digest=contract_digest(**{"path": path}),
        scope=("fs.write",),
        preconditions=("arguments_unchanged", "calibration_current"),
        expires_at=expiry if expiry is not None else time.time() + 3600,
        grant_id=grant_id,
        subject_id="zero-1",
    )


def _issue(reg: GrantRegistry, *, tool="file_write", scope="fs.write",
           params=None, grant_id="grant-permit-1"):
    permit = _permit(grant_id=grant_id)
    grant = grant_from_permit(
        permit, tool=tool, scope=scope,
        params=params if params is not None else {"path": "a"},
        request_id="r1", operation_id="o1")
    reg.issue(grant)
    return permit, grant


_NOOP = lambda _p: {"ok": True, "receipt": "fatto"}


# --------------------------------------------------------------------------- #
# CORRECTNESS SUITE
# --------------------------------------------------------------------------- #


class TestRegistryCorrectness:
    def test_mai_emesso_denied(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        fresh = ActionGrant(**{**g.to_dict(), "id": "g_mai_emesso"})
        res = reg.authorize(fresh.to_dict(), tool="file_write",
                            scope="fs.write", params={"path": "a"})
        assert res.is_err and "grant_not_issued" in res.error

    def test_emesso_una_volta_e_replay_denied(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        ok = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                           params={"path": "a"})
        assert ok.is_ok and ok.value.id == "grant-permit-1"
        replay = reg.authorize(g.to_dict(), tool="file_write",
                               scope="fs.write", params={"path": "a"})
        assert replay.is_err and "grant_used" in replay.error

    def test_copia_alterata_non_vince(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        hacked = ActionGrant(**{**g.to_dict(), "tool": "terminal_exec"})
        res = reg.authorize(hacked.to_dict(), tool="terminal_exec",
                            scope="fs.write", params={"path": "a"})
        assert res.is_err and "grant_registry_mismatch" in res.error

    def test_params_divergenti_denied(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        res = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                            params={"path": "EVIL"})
        assert res.is_err and "params_mismatch" in res.error

    def test_revocato_denied(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        reg.revoke(g.id)
        res = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                            params={"path": "a"})
        assert res.is_err and "grant_revoked" in res.error

    def test_scaduto_denied(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        res = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                            params={"path": "a"}, now=time.time() + 7200)
        assert res.is_err and "grant_expired" in res.error

    def test_status_used_prematuro_non_nega(self):
        # il consumo autoritativo e' il SET, non lo status (regressione TS)
        reg = GrantRegistry()
        _, g = _issue(reg)
        prematuro = ActionGrant(**{**g.to_dict(), "status": "used"})
        ok = reg.authorize(prematuro.to_dict(), tool="file_write",
                           scope="fs.write", params={"path": "a"})
        assert ok.is_ok
        replay = reg.authorize(prematuro.to_dict(), tool="file_write",
                               scope="fs.write", params={"path": "a"})
        assert replay.is_err and "grant_used" in replay.error

    def test_double_registration_rejected(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        assert reg.issue(g).is_err

    def test_authorize_senza_grant_non_esiste(self):
        reg = GrantRegistry()
        res = reg.authorize(None, tool="file_write", scope="fs.write",
                            params={"path": "a"})
        assert res.is_err and "grant_invalid" in res.error


class TestAntiTocTou:
    def test_precondizioni_cambiate_denied(self):
        # autorizzato per {"path":"a"}, al momento dell'uso siamo su {"path":"b"}
        dig_now = contract_digest(**{"path": "b"})
        res = recheck_preconditions(_permit(path="a"),
                                    args_digest_now=dig_now,
                                    scope_now=("fs.write",))
        assert res.is_err and "TOCTOU" in res.error

    def test_precondizioni_ok(self):
        dig_now = contract_digest(**{"path": "a"})
        res = recheck_preconditions(_permit(path="a"),
                                    args_digest_now=dig_now,
                                    scope_now=("fs.write",))
        assert res.is_ok

    def test_scope_fuori_dal_permesso_denied(self):
        dig_now = contract_digest(**{"path": "a"})
        res = recheck_preconditions(_permit(path="a"),
                                    args_digest_now=dig_now,
                                    scope_now=("fs.delete",))
        assert res.is_err and "scope" in res.error

    def test_permit_scaduto_all_uso_denied(self):
        dig_now = contract_digest(**{"path": "a"})
        res = recheck_preconditions(_permit(expiry=time.time() - 10),
                                    args_digest_now=dig_now,
                                    scope_now=("fs.write",))
        assert res.is_err and "scaduto" in res.error


class TestAzioneAutorizza:
    def test_denied_non_tocca_lesecutore(self):
        reg = GrantRegistry()
        called = []

        def spy(p):
            called.append(p)
            return {"ok": True}

        _, g = _issue(reg, params={"path": "a"})
        out = azione_autorizza(
            reg, _permit(), g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "EVIL"}, state={"path": "EVIL"}, executor=spy)
        assert isinstance(out, Failed)
        assert "params_mismatch" in out.error
        assert called == []                      # mai eseguito

    def test_toctou_bloccato_prima_dell_esecuzione(self):
        reg = GrantRegistry()
        # autorizzato per {"path":"a"}; tra emissione e uso il mondo cambia
        # e l'esecutore riceverebbe {"path":"b"} mentre il permit consente "a".
        permit, g = _issue(reg, params={"path": "a"})
        out = azione_autorizza(
            reg, permit, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "b"}, executor=_NOOP)
        assert isinstance(out, Failed)
        assert "TOCTOU" in out.error

    def test_ok_esegue_una_volta_e_ritorna_succeeded(self):
        reg = GrantRegistry()
        calls = []
        permit, g = _issue(reg)
        out = azione_autorizza(
            reg, permit, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "a"},
            executor=lambda p: calls.append(p) or {"ok": True})
        assert isinstance(out, Succeeded)
        assert out.receipt == "file_write:fs.write:grant-permit-1"
        assert len(calls) == 1
        assert calls[0] == {"path": "a"}

    def test_permesso_esplicito_deny_e_review(self):
        reg = GrantRegistry()
        permit, g = _issue(reg)
        deny = Permit(
            action_digest=permit.action_digest,
            arguments_digest=permit.arguments_digest,
            scope=permit.scope, preconditions=permit.preconditions,
            expires_at=permit.expires_at, grant_id="blocked", subject_id="zero-1")
        # un Deny non e' un Permit: si modella come stato separato
        from cascade.contracts_v1 import Deny
        out = azione_autorizza(
            reg, Deny("divieto esplicito"), g.to_dict(),
            tool="file_write", scope="fs.write", params={"path": "a"},
            state={"path": "a"}, executor=_NOOP)
        assert isinstance(out, Failed) and "denied" in out.error

    def test_esecutore_assente_e_indeterminate(self):
        reg = GrantRegistry()
        permit, g = _issue(reg)
        out = azione_autorizza(
            reg, permit, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "a"}, executor=None)
        assert isinstance(out, Indeterminate)
        assert out.reconciliation_ref.startswith("reconcile:executor:")

    def test_timeout_e_indeterminate_non_failed(self):
        reg = GrantRegistry()
        permit, g = _issue(reg)

        def lento(_p):
            raise TimeoutError("risposta persa")

        out = azione_autorizza(
            reg, permit, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "a"}, executor=lento)
        assert isinstance(out, Indeterminate)
        assert "timeout" in out.reconciliation_ref

    def test_esecutore_si_rompe_e_failed_tipizzato(self):
        reg = GrantRegistry()
        permit, g = _issue(reg)

        def rotta(_p):
            raise RuntimeError("crash esecutore")

        out = azione_autorizza(
            reg, permit, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "a"}, executor=rotta)
        assert isinstance(out, Failed)
        assert "RuntimeError" in out.error


# --------------------------------------------------------------------------- #
# COMPATIBILITY SUITE
# --------------------------------------------------------------------------- #


class TestPermitShape:
    def test_13_campi_del_permit(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        assert set(g.to_dict()) == {
            "schema_version", "id", "tool", "scope", "principal", "session_id",
            "request_id", "operation_id", "params", "issued_at", "expires_at",
            "reuse", "status"}
        assert g.schema_version == GRANT_SCHEMA_VERSION
        assert g.reuse == "once" and g.status == "active"

    def test_from_dict_roundtrip_identity(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        parsed, err = ActionGrant.from_dict(g.to_dict())
        assert err == "" and parsed == g

    def test_from_dict_manca_campo(self):
        d = {"a": 1}
        _, err = ActionGrant.from_dict(d)
        assert "campo mancante" in err

    def test_destrutturazione_da_permit(self):
        permit = _permit(path="a")
        grant = grant_from_permit(
            permit, tool="file_write", scope="fs.write",
            params={"path": "a"}, request_id="r1", operation_id="o1")
        assert grant.id == permit.grant_id
        assert grant.tool == "file_write" and grant.scope == "fs.write"
        assert grant.principal == "cascade"
        assert grant.params == {"path": "a"}

    def test_deep_compare_params_indipendente_dall_ordine(self):
        reg = GrantRegistry()
        _, g = _issue(reg, params={"path": "a", "backup": True})
        ok = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                           params={"backup": True, "path": "a"})
        assert ok.is_ok

    def test_esiti_sempre_tipizzati_mai_eccezioni(self):
        reg = GrantRegistry()
        permission = _permit()
        g = ActionGrant(
            id="x", tool="file_write", scope="fs.write", params={"path": "a"},
            issued_at="2026-01-01T00:00:00.000Z",
            expires_at="2026-01-01T00:00:00.000Z")
        out = azione_autorizza(
            reg, permission, g.to_dict(), tool="file_write", scope="fs.write",
            params={"path": "a"}, state={"path": "a"}, executor=_NOOP)
        assert isinstance(out, (Succeeded, Failed, Indeterminate))

    def test_registry_reset_pulisce_consumi(self):
        reg = GrantRegistry()
        _, g = _issue(reg)
        assert reg.authorize(g.to_dict(), tool="file_write",
                             scope="fs.write", params={"path": "a"}).is_ok
        assert g.id in reg._consumed
        reg.reset()
        assert g.id not in reg._consumed
        # reset toglie anche i record: ora e' grant_not_issued, non grant_used
        res = reg.authorize(g.to_dict(), tool="file_write", scope="fs.write",
                            params={"path": "a"})
        assert res.is_err and "grant_not_issued" in res.error