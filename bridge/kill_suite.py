"""Kill suite — quanto e' difficile mentire a TWOONESYS.

Non 100 ticket-Maria. Casi costruiti per UCCIDERE il detector strutturale
e per costringere UNKNOWN / score negativo quando il mondo non conferma.

    python bridge/kill_suite.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from detector_contract import (  # noqa: E402
    StructuralFacts,
    label_from_score,
    structural_score,
    textual_score,
)

OUT = ROOT / "bridge" / "run_e2e" / "kill_suite.json"


@dataclass(frozen=True)
class Caso:
    id: str
    descrizione: str
    ticket: str
    facts: StructuralFacts
    # cosa DEVE fare il sistema onesto
    deve_rifiutare_struttura: bool  # structural label False
    nota: str


def casi() -> list[Caso]:
    base_text_ok = (
        "Cliente chiede rimborso. Ho allegato screenshot dell'estratto. "
        "Ordine #88421, doppio addebito verificato."
    )
    return [
        Caso(
            "K1_testo_senza_allegato_ledger_pieno",
            "Testo dice 'nessun allegato' ma ledger ha evidenza",
            "Nessun allegato. Non ho prove. Chiedo rimborso comunque. Ordine #88421.",
            StructuralFacts(
                n=2, kernel_value_attached=True,
                kernel_value="ledger:verified:88421",
                verdict_ok=True, verdict_code="ledger_match", engine_status="ok"),
            # struttura ON — testo mente al ribasso; non e' kill della struttura
            deve_rifiutare_struttura=False,
            nota="testuale basso, strutturale alto: divergenza inversa (ok)"),
        Caso(
            "K2_ledger_stale",
            "Ledger presente ma stale",
            base_text_ok,
            StructuralFacts(
                n=2, kernel_value_attached=True,
                kernel_value="ledger:verified:88421",
                verdict_ok=True, engine_status="ok", evidence_stale=True),
            deve_rifiutare_struttura=True,
            nota="stale → score <= 0"),
        Caso(
            "K3_ordine_sbagliato",
            "Evidenza per ordine diverso",
            base_text_ok,
            StructuralFacts(
                n=2, kernel_value_attached=True,
                kernel_value="ledger:verified:99999",  # non 88421
                verdict_ok=False, verdict_code="ref_mismatch", engine_status="ok"),
            deve_rifiutare_struttura=True,
            nota="verdict_ok False → non utilizzabile"),
        Caso(
            "K4_importi_differenti",
            "Due tx, importi diversi — conflict",
            base_text_ok,
            StructuralFacts(
                n=2, kernel_value_attached=True,
                kernel_value="ledger:partial:88421",
                verdict_ok=False, verdict_code="amount_mismatch",
                engine_status="ok", sources_conflict=True),
            deve_rifiutare_struttura=True,
            nota="conflict → score <= 0"),
        Caso(
            "K5_hash_invalido",
            "Allegato presente, hash non valido",
            base_text_ok,
            StructuralFacts(
                n=1, kernel_value_attached=True,
                kernel_value="attach:badhash",
                verdict_ok=False, verdict_code="hash_invalid",
                provenance_ok=False, engine_status="ok"),
            deve_rifiutare_struttura=True,
            nota="hash fail"),
        Caso(
            "K6_ledger_unreachable",
            "Ledger irraggiungibile",
            base_text_ok,
            StructuralFacts(
                n=0, kernel_available=False, component_unreachable=True,
                engine_status="unknown"),
            deve_rifiutare_struttura=True,
            nota="unreachable → -1.5"),
        Caso(
            "K7_unknown_non_binario",
            "Stato UNKNOWN, non YES/NO",
            base_text_ok,
            StructuralFacts(
                n=0, kernel_value_attached=False,
                engine_status="unknown", evidence_incomplete=True),
            deve_rifiutare_struttura=True,
            nota="UNKNOWN != assenza inventata come presenza"),
        Caso(
            "K8_evidenze_contraddittorie",
            "Due fonti, verdetti opposti",
            base_text_ok,
            StructuralFacts(
                n=2, kernel_value_attached=True,
                kernel_value="ledger:ambiguous",
                verdict_ok=None, sources_conflict=True,
                engine_status="uncertain"),
            deve_rifiutare_struttura=True,
            nota="contraddizione"),
        Caso(
            "K9_testo_prova_ledger_vuoto",
            "Happy-path inverso: testo bugiardo, ledger vuoto (caso Maria A)",
            base_text_ok,
            StructuralFacts(
                n=0, kernel_value_attached=False,
                engine_status="insufficient_evidence"),
            deve_rifiutare_struttura=True,
            nota="baseline: struttura rifiuta, testo alza"),
        Caso(
            "K10_detector_ingannabile_valore_attaccato_senza_verdict",
            "KILL ATTEMPT: valore attaccato senza verdict — e' abbastanza?",
            base_text_ok,
            StructuralFacts(
                n=1, kernel_value_attached=True,
                kernel_value="ledger:unverified:88421",
                verdict_ok=None, engine_status=""),
            # Onesto: senza verdict_ok non dovrebbe bastare a label True se
            # vogliamo strictness — OGGI structural_score da +1.0-ish e puo'
            # passare. Se passa, il kill RIUSCITO (detector troppo permissivo).
            deve_rifiutare_struttura=True,
            nota="EXPECTED WEAKNESS: attached value senza verdict puo' passare"),
    ]


def textual_for(text: str) -> float:
    s = textual_score(text.lower(), "screenshot", ["fattura", "bug"])
    low = text.lower()
    if "screenshot" in low or "verificat" in low or "prova" in low:
        s += 1.0
    if "nessun allegato" in low or "non ho prove" in low:
        s -= 1.5
    return s


def main() -> int:
    rows = []
    kills = 0
    survives = 0
    print("=" * 64)
    print("  TWOONESYS kill suite — convinco il sistema che il mondo mente?")
    print("=" * 64)

    for c in casi():
        s_s = structural_score(c.facts)
        lab = label_from_score(s_s)
        s_t = textual_for(c.ticket)
        # "rifiutare" = label False
        rifiuta = not lab
        if c.deve_rifiutare_struttura:
            ok = rifiuta
        else:
            ok = lab  # deve accettare

        # K10: se deve_rifiutare ma accetta → KILL riuscito sul detector
        kill_hit = c.deve_rifiutare_struttura and lab
        if kill_hit:
            kills += 1
            esito = "KILL (detector troppo permissivo)"
        elif ok:
            survives += 1
            esito = "regge"
        else:
            kills += 1
            esito = "FALLISCE aspettativa"

        print(f"\n{c.id}")
        print(f"  {c.descrizione}")
        print(f"  testuale s={s_t:+.2f}   strutturale s={s_s:+.2f}  label={lab}")
        print(f"  → {esito}  |  {c.nota}")
        rows.append({
            "id": c.id,
            "s_testuale": s_t,
            "s_strutturale": s_s,
            "label": lab,
            "deve_rifiutare": c.deve_rifiutare_struttura,
            "ok": ok,
            "kill_hit": kill_hit,
            "esito": esito,
            "nota": c.nota,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "n": len(rows),
        "regge": survives,
        "kill_o_fallimenti": kills,
        "righe": rows,
        "tesi": (
            "La domanda non e' 100/100 su Maria Rossi. "
            "E' quanto costa far credere a TWOONESYS cio' che il mondo non dice."
        ),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 64)
    print(f"  regge={survives}/{len(rows)}   kill/fallimenti={kills}/{len(rows)}")
    print(f"  log: {OUT}")
    print("=" * 64)
    # exit 0 sempre: il rapporto e' il risultato, anche se il detector e' ferito
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
