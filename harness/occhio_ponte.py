"""Ponte: una decisione già presa entra in CASCADE.

Il numero (probabilità, confidenza) non sceglie allow o deny.
Lo decide solo la policy sul path. Il modello non è in questo file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .guarded import ActionDenied, guarded
from .receipt import ActionReceipt
from .signing import KeyRegistry, SigningIdentity

_TIPI = frozenset({"choice", "noul", "score"})
_CAMPI = {
    "choice": ("choice",),
    "noul": ("noul",),
    "score": ("score",),
}


def decisione_gia_presa(decisione: dict[str, Any]) -> dict[str, Any]:
    """Tiene il verdetto. Butta probabilità e frasi."""
    if not isinstance(decisione, dict):
        raise ValueError("decisione non è un oggetto")
    tipo = decisione.get("type")
    if tipo not in _TIPI:
        raise ValueError("type fuori da choice, noul, score")
    for valore in decisione.values():
        if isinstance(valore, str) and len(valore.split()) > 8:
            raise ValueError("frase in uscita")
    out: dict[str, Any] = {"type": tipo}
    for campo in _CAMPI[tipo]:
        if campo not in decisione:
            raise ValueError(f"manca {campo}")
        out[campo] = decisione[campo]
    return out


def consegna(
    decisione: dict[str, Any],
    path: str | Path,
    *,
    identity: SigningIdentity | None = None,
    registry: KeyRegistry | None = None,
    receipt_dir: str | Path | None = None,
) -> ActionReceipt:
    """Scrive il verdetto nel path. CASCADE autorizza o nega, poi firma."""
    payload = json.dumps(decisione_gia_presa(decisione), ensure_ascii=False)

    @guarded(identity=identity, registry=registry, receipt_dir=receipt_dir)
    def scrivi(path, contenuto):
        Path(path).write_text(contenuto, encoding="utf-8")

    try:
        return scrivi(path, payload)
    except ActionDenied:
        raise
