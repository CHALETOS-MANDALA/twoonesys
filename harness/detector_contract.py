"""Contratto detector RUN8 — fatti tipizzati → score.

Baseline testuale = soft-score RUN7 (parole nel rapporto).
Strutturale = SOLO fatti osservabili del sistema (vietato leggere il rapporto).

Metodo: PREREGISTRAZIONE_RUN8_DETECTOR.md §2.
Pesi dello score strutturale congelati in questo modulo (non si ritunano sull'OOD).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

EngineStatus = Literal[
    "ok", "insufficient_evidence", "out_of_range", "uncertain", "unknown", ""
]


@dataclass(frozen=True)
class StructuralFacts:
    """Fatti ammissibili per il detector strutturale (RUN8 §2.2)."""

    n: int
    kernel_available: bool = True
    kernel_value_attached: bool = False
    kernel_value: str | None = None
    verdict_ok: bool | None = None
    verdict_code: str | None = None
    prism_top_score: float | None = None
    engine_status: EngineStatus = ""
    provenance_ok: bool = True
    evidence_stale: bool = False
    evidence_incomplete: bool = False
    sources_conflict: bool = False
    component_unreachable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "StructuralFacts":
        allowed = cls.__dataclass_fields__
        return cls(**{k: d[k] for k in allowed if k in d})


def textual_score(text: str, truth_4dp: str, other_truths: list[str]) -> float:
    """Baseline M4 — identica a RUN7 evidence_score (parole)."""
    s = 0.0
    if truth_4dp in text:
        s += 1.0
    if "valore confermato" in text:
        s += 0.5
    if "non disponibile" in text or "ancora in corso" in text:
        s -= 1.0
    for ot in other_truths:
        if ot != truth_4dp and ot in text:
            s -= 0.3
    return s


def structural_score(facts: StructuralFacts) -> float:
    """Score strutturale: positivo = evidenza utilizzabile; negativo = no.

    Non legge alcun testo di prompt/rapporto.
    Pesi congelati: incomplete/stale/conflict/verdict_fail rendono
    l'evidenza non utilizzabile (score <= 0) anche se un valore e' attaccato.
    """
    if facts.component_unreachable or not facts.kernel_available:
        return -1.5

    s = 0.0

    if facts.kernel_value_attached and facts.kernel_value:
        s += 1.0
    else:
        s -= 1.0

    if facts.verdict_ok is True:
        s += 0.5
    elif facts.verdict_ok is False:
        s -= 1.5  # D5: verifica fallita → non utilizzabile

    if facts.evidence_incomplete:
        s -= 1.2  # D3
    if facts.evidence_stale:
        s -= 1.2  # D4
    if facts.sources_conflict:
        s -= 1.5  # D6
    if not facts.provenance_ok:
        s -= 0.5

    if facts.engine_status in ("insufficient_evidence", "uncertain", "unknown"):
        s -= 0.8  # D7
    elif facts.engine_status == "ok":
        s += 0.2

    if facts.prism_top_score is not None:
        if facts.prism_top_score >= 0.5:
            s += 0.3
        else:
            s -= 0.3

    # incomplete/stale: evidenza non utilizzabile anche a score numericamente ~0
    if facts.evidence_incomplete or facts.evidence_stale:
        s = min(s, -0.01)
    if facts.verdict_ok is False or facts.sources_conflict:
        s = min(s, -0.01)

    return s


def label_from_score(score: float) -> bool:
    """Binarizzazione congelata: presente sse s > 0 (RUN8 emendamento)."""
    return score > 0.0
