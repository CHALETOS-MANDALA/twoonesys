"""@guarded + cascade verify: agente bloccato, ricevuta verificabile."""

import json
import subprocess
import sys
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


def test_verify_receipt_usa_registro_pubblico_di_default(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    pub = tmp_path / "public_keys.json"
    monkeypatch.setattr("cascade.signing.DEFAULT_PUBLIC_KEYS", pub)

    @guarded(receipt_dir=tmp_path / "receipts")
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    with pytest.raises(ActionDenied) as caught:
        scrivi(tmp_path / "outside.txt", "no")
    ok, msg = verify_receipt(caught.value.receipt)
    assert ok is True
    assert "authorized=False" in msg


def test_exec_interprete_estraneo_non_parte(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    script = sandbox / "ok.py"
    script.write_text("print('no')\n", encoding="utf-8")
    ran = {"n": 0}

    @guarded(policy="exec.sandbox", receipt_dir=tmp_path / "receipts")
    def lancia(argv, cwd):
        ran["n"] += 1
        return subprocess.run(argv, cwd=cwd, shell=False, check=True)

    with pytest.raises(ActionDenied) as caught:
        lancia(["python", str(script)], cwd=str(sandbox))
    assert ran["n"] == 0
    assert caught.value.receipt.tool == "exec"
    assert caught.value.receipt.authorized is False


def test_exec_script_nel_sandbox_parte(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    script = sandbox / "ok.py"
    marker = sandbox / "ran.txt"
    script.write_text(
        "from pathlib import Path\nPath('ran.txt').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )

    @guarded(policy="exec.sandbox", receipt_dir=tmp_path / "receipts")
    def lancia(argv, cwd):
        return subprocess.run(argv, cwd=cwd, shell=False, check=True)

    rec = lancia([sys.executable, str(script)], cwd=str(sandbox))
    assert marker.read_text(encoding="utf-8") == "ok"
    assert rec.authorized is True
    assert rec.outcome is True
    assert rec.policy == "exec.sandbox"


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
