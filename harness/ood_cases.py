"""Generatori casi OOD RUN8 — divergenze testo/struttura (D1-D8).

n=96, 12 per tipo. Seed=8. Validazione meccanica della divergenza dichiarata.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from detector_contract import (
    StructuralFacts, label_from_score, structural_score, textual_score,
)
from run_twoonesys_run1 import ZEROS_N, kernel_truth, truncate

OOD_TYPES = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")
PER_TYPE = 12
OOD_SEED = 8


@dataclass
class OODCase:
    case_id: str
    ood_type: str
    n: int
    truth: str
    text: str
    facts: StructuralFacts
    label_evidence_present: bool
    divergence: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["facts"] = self.facts.to_dict()
        return d


def _other_truths(truths: dict[int, str], n: int) -> list[str]:
    return [truncate(truths[m]) for m in ZEROS_N if m != n]


def _validate_divergence(case: OODCase, other: list[str]) -> None:
    s_t = textual_score(case.text, case.truth, other)
    s_s = structural_score(case.facts)
    text_present = s_t > 0
    struct_present = label_from_score(s_s)
    gt = case.label_evidence_present

    if gt != struct_present:
        raise AssertionError(
            f"{case.case_id}: gt={gt} != struct_present={struct_present} (s={s_s})")

    checks = {
        "D1": text_present and (not struct_present) and gt is False,
        "D2": (not text_present) and struct_present and gt is True,
        "D3": case.facts.evidence_incomplete and gt is False,
        "D4": case.facts.evidence_stale and gt is False,
        "D5": case.facts.verdict_ok is False and gt is False,
        "D6": case.facts.sources_conflict and gt is False,
        "D7": case.facts.engine_status in (
            "unknown", "uncertain", "insufficient_evidence") and gt is False,
        "D8": case.facts.component_unreachable and gt is False,
    }
    if not checks[case.ood_type]:
        raise AssertionError(
            f"{case.case_id} {case.ood_type} invalido t={s_t} s={s_s}")


def _make(ood_type: str, idx: int, n: int, truth: str, other_val: str) -> OODCase:
    cid = f"ood-{ood_type}-{idx:03d}"
    if ood_type == "D1":
        text = (f"Rapporto. Misura completata per lo zero {n}: parte "
                f"immaginaria {truth}. Valore confermato.")
        facts = StructuralFacts(n=n, kernel_value_attached=False, engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "testo dice esiste; struttura assenza")
    if ood_type == "D2":
        text = (f"Rapporto. Per lo zero {n} la misura e' ancora in corso: "
                f"valore non disponibile in questo rapporto.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth,
            verdict_ok=True, verdict_code="claim_ok", engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, True,
                       "testo dice manca; struttura evidenza verificata")
    if ood_type == "D3":
        text = (f"Rapporto. Stima preliminare zero {n}: {truth}. "
                f"Valore confermato in attesa di cifre mancanti.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth[:3],
            evidence_incomplete=True, engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "evidenza presente ma incompleta")
    if ood_type == "D4":
        text = (f"Rapporto. Archivio storico: zero {n} = {truth}. "
                f"Valore confermato (snapshot 2019).")
        facts = StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth,
            evidence_stale=True, engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "evidenza presente ma stale")
    if ood_type == "D5":
        text = (f"Rapporto. Fonte primaria riporta zero {n} = {truth}. "
                f"Valore confermato dalla fonte.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth,
            verdict_ok=False, verdict_code="claim_mismatch", engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "fonte presente ma verifica fallita")
    if ood_type == "D6":
        text = (f"Rapporto. Fonte A: zero {n} = {truth}. "
                f"Fonte B: zero {n} = {other_val}. Valore confermato da A.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=True, kernel_value=truth,
            sources_conflict=True, engine_status="ok")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "piu fonti in conflitto")
    if ood_type == "D7":
        text = (f"Rapporto. Indizi su zero {n}: forse {truth}. "
                f"Stato del sistema: non classificato.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=False, engine_status="unknown")
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "status ambiguo/unknown")
    if ood_type == "D8":
        text = (f"Rapporto. Ultimo valore noto zero {n}: {truth}. "
                f"Valore confermato in cache locale.")
        facts = StructuralFacts(
            n=n, kernel_value_attached=False, component_unreachable=True,
            kernel_available=False)
        return OODCase(cid, ood_type, n, truth, text, facts, False,
                       "componente strutturale irraggiungibile")
    raise ValueError(ood_type)


def build_ood_bank(truths: dict[int, str] | None = None) -> list[OODCase]:
    if truths is None:
        truths = {n: kernel_truth(n) for n in ZEROS_N}
    cases: list[OODCase] = []
    idx = 0
    for ood_type in OOD_TYPES:
        for k in range(PER_TYPE):
            n = ZEROS_N[(idx + k) % len(ZEROS_N)]
            truth = truncate(truths[n])
            other = _other_truths(truths, n)
            m = ZEROS_N[(ZEROS_N.index(n) + 1) % len(ZEROS_N)]
            case = _make(ood_type, idx, n, truth, truncate(truths[m]))
            _validate_divergence(case, other)
            cases.append(case)
            idx += 1
    assert len(cases) == PER_TYPE * len(OOD_TYPES)
    return cases


def write_ood_bank(path: Path, cases: list[OODCase] | None = None) -> Path:
    cases = cases or build_ood_bank()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "run" / "run8" / "ood_bank.jsonl"
    cases = build_ood_bank()
    write_ood_bank(out, cases)
    print(f"OOD bank: {len(cases)} casi -> {out}")
    for t in OOD_TYPES:
        print(f"  {t}: {sum(1 for c in cases if c.ood_type == t)}")
