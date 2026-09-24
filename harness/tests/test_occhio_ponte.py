"""La probabilità non sposta la policy."""

import json
from pathlib import Path

from cascade import ActionDenied, verify_receipt
from cascade.occhio_ponte import consegna, decisione_gia_presa
from cascade.signing import KeyRegistry, SigningIdentity


def _ident():
    ident = SigningIdentity.generate()
    keys = KeyRegistry()
    keys.register(ident)
    return ident, keys


def test_probabilita_alta_o_bassa_stesso_verdetto(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("CASCADE_SANDBOX", str(sandbox))
    ident, keys = _ident()
    dentro = sandbox / "decisione.json"
    fuori = tmp_path / "fuori.json"

    for confidenza in (0.01, 0.99):
        rec = consegna(
            {"type": "choice", "choice": "red", "confidence": confidenza,
             "probabilities": {"red": confidenza}},
            dentro,
            identity=ident, registry=keys, receipt_dir=tmp_path / "r",
        )
        assert rec.authorized is True
        corpo = json.loads(dentro.read_text(encoding="utf-8"))
        assert corpo == {"type": "choice", "choice": "red"}
        assert "confidence" not in corpo
        ok, _ = verify_receipt(rec, keys)
        assert ok is True

        with __import__("pytest").raises(ActionDenied) as caught:
            consegna(
                {"type": "noul", "noul": True, "confidence": confidenza},
                fuori,
                identity=ident, registry=keys,
            )
        assert caught.value.receipt.authorized is False
        assert not fuori.exists()


def test_frase_non_entra():
    try:
        decisione_gia_presa({
            "type": "choice",
            "choice": "the item is red and also slightly damaged on the left",
        })
    except ValueError as exc:
        assert "frase" in str(exc)
    else:
        raise AssertionError("la frase doveva essere rifiutata")
