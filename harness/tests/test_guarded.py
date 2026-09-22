"""@guarded + cascade verify: agente bloccato, ricevuta verificabile."""

import json
from pathlib import Path

import pytest

from cascade import ActionDenied, guarded, verify_receipt
from cascade.cli import main as cascade_main
from cascade.signing import KeyRegistry, SigningIdentity


def test_scrittura_fuori_sandbox_viene_bloccata(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    ident = SigningIdentity.generate()
    keys = KeyRegistry()
    keys.register(ident)

    @guarded(identity=ident, registry=keys, receipt_dir=tmp_path / "receipts")
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    outside = tmp_path / "outside.txt"
    with pytest.raises(ActionDenied) as caught:
        scrivi(outside, "segreto")
    assert not outside.exists()
    rec = caught.value.receipt
    assert rec.authorized is False
    ok, _ = verify_receipt(rec, keys)
    assert ok is True


def test_scrittura_in_sandbox_esegue_e_ricevuta_verificabile(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    ident = SigningIdentity.generate()
    keys = KeyRegistry()
    keys.register(ident)
    receipts = tmp_path / "receipts"

    @guarded(identity=ident, registry=keys, receipt_dir=receipts)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    target = sandbox / "ok.txt"
    rec = scrivi(target, "ciao")
    assert target.read_text(encoding="utf-8") == "ciao"
    assert rec.authorized is True
    assert rec.outcome is True
    ok, msg = verify_receipt(rec, keys)
    assert ok is True
    assert "ok" in msg
    saved = next(receipts.glob("*.json"))
    disk_keys = tmp_path / "public.json"
    disk_keys.write_text(
        json.dumps({ident.key_id: ident.public_bytes.hex()}),
        encoding="utf-8")
    assert cascade_main(["verify", str(saved), "--registry", str(disk_keys)]) == 0


def test_chiave_sconosciuta_non_e_verificabile():
    ident = SigningIdentity.generate()
    other = KeyRegistry()
    from cascade.receipt import issue_receipt
    rec = issue_receipt(
        request_id="x", policy="fs.write.sandbox", tool="fs.write",
        scope="sandbox", authorized=False, outcome=False, path="no",
        identity=ident, registry=None)
    ok, message = verify_receipt(rec, other)
    assert ok is False
    assert "sconosciuta" in message or "non valida" in message
