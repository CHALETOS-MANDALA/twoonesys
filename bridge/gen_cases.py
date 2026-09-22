"""Batteria generalizzazione — congelata con PREREGISTRAZIONE_GENERALIZZAZIONE.md.

24 casi. Non cloni di Maria. Non ritunare dopo aver visto i numeri.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from detector_contract import StructuralFacts

Tipo = Literal[
    "routing_chiaro",
    "divergenza_ledger_vuoto",
    "allineato_ledger_pieno",
    "kill_strutturale",
    "ambiguo_gold",
]


@dataclass(frozen=True)
class CasoGen:
    id: str
    tipo: Tipo
    ticket: str
    gold_reparto: str | None  # None se ambiguo
    gold_chiaro: bool
    expect_structural_usable: bool
    facts: StructuralFacts
    maria_like: bool = False
    note: str = ""


def _ok(ref: str) -> StructuralFacts:
    return StructuralFacts(
        n=1, kernel_value_attached=True,
        kernel_value=f"ledger:verified:{ref}",
        verdict_ok=True, verdict_code="ledger_match", engine_status="ok")


def _vuoto() -> StructuralFacts:
    return StructuralFacts(
        n=0, kernel_value_attached=False,
        engine_status="insufficient_evidence")


def _stale(ref: str) -> StructuralFacts:
    return StructuralFacts(
        n=1, kernel_value_attached=True,
        kernel_value=f"ledger:verified:{ref}",
        verdict_ok=True, engine_status="ok", evidence_stale=True)


def _mismatch(ref: str) -> StructuralFacts:
    return StructuralFacts(
        n=1, kernel_value_attached=True,
        kernel_value=f"ledger:verified:{ref}",
        verdict_ok=False, verdict_code="ref_mismatch", engine_status="ok")


def _conflict() -> StructuralFacts:
    return StructuralFacts(
        n=2, kernel_value_attached=True,
        kernel_value="ledger:ambiguous",
        verdict_ok=None, sources_conflict=True, engine_status="uncertain")


def _unreachable() -> StructuralFacts:
    return StructuralFacts(
        n=0, kernel_available=False, component_unreachable=True,
        engine_status="unknown")


def _unknown() -> StructuralFacts:
    return StructuralFacts(
        n=0, kernel_value_attached=False,
        engine_status="unknown", evidence_incomplete=True)


def _badhash() -> StructuralFacts:
    return StructuralFacts(
        n=1, kernel_value_attached=True,
        kernel_value="attach:badhash",
        verdict_ok=False, verdict_code="hash_invalid",
        provenance_ok=False, engine_status="ok")


def _attached_no_verdict() -> StructuralFacts:
    """K10 — ferita nota: può passare. expect_structural_usable=False per G2."""
    return StructuralFacts(
        n=1, kernel_value_attached=True,
        kernel_value="ledger:unverified:x",
        verdict_ok=None, engine_status="")


def casi() -> list[CasoGen]:
    return [
        # --- routing chiaro (domini diversi) ---
        CasoGen(
            "G01", "routing_chiaro",
            "Fattura di settembre non arriva via PEC. Partita IVA 124578, "
            "serve copia XML entro venerdi per il commercialista.",
            "billing", True, False, _vuoto(),
            note="fatturazione senza claim di screenshot"),
        CasoGen(
            "G02", "routing_chiaro",
            "Crash loop su iOS 17.5 aprendo i messaggi. Reinstallato due volte. "
            "Log allegato crashlytics id 9f3a.",
            "technical", True, False, _vuoto()),
        CasoGen(
            "G03", "routing_chiaro",
            "Vorremmo un preventivo Enterprise per 40 seat, fatturazione annuale, "
            "confronto con competitor Z. Contatto: procurement@acme.test",
            "sales", True, False, _vuoto()),
        CasoGen(
            "G04", "routing_chiaro",
            "Chargeback Visa 87 EUR sul merchant mid-4412. Serve dispute package "
            "entro 5 giorni lavorativi. Case bank #VB-22091.",
            "billing", True, False, _vuoto()),
        CasoGen(
            "G05", "routing_chiaro",
            "Webhook checkout.completed non arriva da 03:00 UTC. Timeout 30s lato "
            "nostro. Environment production eu-west.",
            "technical", True, False, _vuoto()),
        CasoGen(
            "G06", "routing_chiaro",
            "Interessati al piano Team, siamo 6, vogliamo sapere se lo sconto "
            "nonprofit si applica anche al add-on analytics.",
            "sales", True, False, _vuoto()),
        CasoGen(
            "G07", "routing_chiaro",
            "Richiesta nota di credito per ordine OC-55102: merce resa danneggiata "
            "in magazzino, DDT 8891. Nessuna disputa carta.",
            "billing", True, False, _vuoto()),
        CasoGen(
            "G08", "routing_chiaro",
            "After latest deploy, login SSO SAML assertion fails with status "
            "Responder. IdP Okta, SP entity-id prod.",
            "technical", True, False, _vuoto()),
        CasoGen(
            "G09", "routing_chiaro",
            "Demo week next Tuesday for the legal team — need a live walkthrough "
            "of e-sign workflow and pricing tiers.",
            "sales", True, False, _vuoto()),
        CasoGen(
            "G10", "routing_chiaro",
            "Addebito ricorrente non cancellato dopo disdetta del 12/08. "
            "Contratto C-7781. Chiedo stop e rimborso pro-rata.",
            "billing", True, False, _vuoto()),
        CasoGen(
            "G11", "routing_chiaro",
            "Dashboard latency p99 > 4s since Friday. Region us-east-1. "
            "No recent config change on our side.",
            "technical", True, False, _vuoto()),
        CasoGen(
            "G12", "routing_chiaro",
            "Partnership white-label: vogliamo listino reseller e MDF Q4. "
            "Siamo rivenditori certificati dal 2023.",
            "sales", True, False, _vuoto()),

        # --- divergenza: testo parla di prove, ledger vuoto ---
        CasoGen(
            "G13", "divergenza_ledger_vuoto",
            "Vi mando lo screenshot del doppio addebito 49,90€ ordine #88421. "
            "E' tutto verificato dal mio estratto conto. Rimborso subito.",
            "billing", True, False, _vuoto(),
            maria_like=True,
            note="unico maria-like #1"),
        CasoGen(
            "G14", "divergenza_ledger_vuoto",
            "Ho la prova fotografica del colli danneggiato e il tracking dice "
            "consegnato. Rimborso o sostituzione, allegato tutto in chat.",
            "billing", True, False, _vuoto(),
            note="prova dichiarata, ledger vuoto — non maria"),
        CasoGen(
            "G15", "divergenza_ledger_vuoto",
            "Confirmed with my bank: duplicate SEPA of 120.00 on mandate UM-12. "
            "Screenshot attached in portal. Please reverse today.",
            "billing", True, False, _vuoto()),

        # --- allineato: ledger pieno + testo con prove ---
        CasoGen(
            "G16", "allineato_ledger_pieno",
            "Vi mando lo screenshot del doppio addebito 49,90€ ordine #88421. "
            "E' tutto verificato dal mio estratto conto. Rimborso subito.",
            "billing", True, True, _ok("88421"),
            maria_like=True,
            note="unico maria-like #2 — stesso testo di G13, ledger SI"),
        CasoGen(
            "G17", "allineato_ledger_pieno",
            "Confirmed with my bank: duplicate SEPA of 120.00 on mandate UM-12. "
            "Screenshot attached in portal. Please reverse today.",
            "billing", True, True, _ok("UM-12")),

        # --- kill strutturale ---
        CasoGen(
            "G18", "kill_strutturale",
            "Rimborso ordine #100. Ho screenshot. Tutto verificato.",
            "billing", True, False, _stale("100"),
            note="ledger stale"),
        CasoGen(
            "G19", "kill_strutturale",
            "Rimborso ordine #100. Ho screenshot. Tutto verificato.",
            "billing", True, False, _mismatch("999"),
            note="ref mismatch"),
        CasoGen(
            "G20", "kill_strutturale",
            "Due addebiti diversi importi sullo stesso giorno. Allegati in PDF.",
            "billing", True, False, _conflict(),
            note="sources conflict"),
        CasoGen(
            "G21", "kill_strutturale",
            "Upload ricevuto ma il sistema dice hash invalid. Cosa faccio?",
            "technical", True, False, _badhash()),
        CasoGen(
            "G22", "kill_strutturale",
            "Non so se il ledger risponde. L'operatore ha messo UNKNOWN.",
            "billing", True, False, _unknown()),
        CasoGen(
            "G23", "kill_strutturale",
            "Timeout verso il servizio ledger. Riprovare piu' tardi.",
            "technical", True, False, _unreachable()),

        # --- ambiguo (escluso da G1) ---
        CasoGen(
            "G24", "ambiguo_gold",
            "Il cliente chiede chiarimenti sul contratto e anche un reset password "
            "perche' non entra in area riservata fatture.",
            None, False, False, _vuoto(),
            note="billing+technical mescolati — fuori G1"),
    ]


def anti_maria_ok(cs: list[CasoGen]) -> tuple[bool, str]:
    templates = {c.ticket.strip() for c in cs}
    maria = sum(1 for c in cs if c.maria_like)
    ok = len(templates) >= 8 and maria <= 2
    return ok, f"template_distinti={len(templates)} maria_like={maria}"


def as_public_dict(c: CasoGen) -> dict[str, Any]:
    return {
        "id": c.id,
        "tipo": c.tipo,
        "gold_reparto": c.gold_reparto,
        "gold_chiaro": c.gold_chiaro,
        "expect_structural_usable": c.expect_structural_usable,
        "maria_like": c.maria_like,
        "note": c.note,
        "ticket_preview": c.ticket[:80],
    }
