"""CASCADE - Integrazione LBP2 passo 3: barriera strutturata sui claim.

Traduce in CASCADE il contratto dei claim documentali/numerici (LBP2
CONTRATTI_V1 §8) sopra l'evidenza prodotta dal kernel di `matematica/evidenza`.
Non importa codice di `matematica`: consuma SOLO lo schema JSON dell'evidenza
(stessa forma: tool / args / exit_code / stdout_hash / parsed / fact) - vedi
`check_numeric_claim`.

Missione della barriera (non cambia rispetto all'originale):
    NO TOOL EVIDENCE => NO TOOL CLAIM.

Tre hash distinti (LBP2 §11.1) - QUI si dichiara esplicitamente qual e' il
legame claim <-> evidenza:
    * transport_bytes_hash  - integrita' dei byte trasmessi (fuori dal claim);
    * canonical_payload_hash - il riferimento PRIMARIO del claim numerico
        (`evidence_ref` = sha256(canonical_json(evidenza))). Eredita da
        matematica l'ammissione del `stdout_hash` come riferimento legacy;
    * semantic_equivalence  - SOLO equivalenza relativa (normalizzazione di
        spazi/case per testo; canonical_json per strutture). Mai uguaglianza
        semantica piena: statene lontani per i link prova->claim.

Regole di valore (LBP2 §8.1): la cifra del claim deve essere un PREFISSO
corretto delle cifre dell'evidenza (il troncamento e' tollerato,
l'alterazione no). L'oggetto del claim si distingue per `subject_id` + ref,
mai contando le cifre nel testo.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from cascade.contracts import canonical_json, sha256_hex

# --------------------------------------------------------------------------- #
# hash distinti (LBP2 §11.1)
# --------------------------------------------------------------------------- #

DIGEST = "sha256"
PRIMARY_HASH_FIELD = "canonical_payload_hash"


def transport_bytes_hash(payload: bytes) -> str:
    """Integrita' dei byte trasmessi: non va usata come legame claim<->evidenza."""
    return hashlib.sha256(payload).hexdigest()


def canonical_payload_hash(obj: Any) -> str:
    """Riferimento stabile per qualunque payload strutturato."""
    return sha256_hex(obj)


def semantic_equivalence(a: Any, b: Any) -> bool:
    """Equivalenza SOLO relativa: testo normalizzato (spazi/case) o dict con
    stessa forma canonica. Non e' uguaglianza semantica."""
    if isinstance(a, str) and isinstance(b, str):
        return _normalized(a) == _normalized(b)
    return canonical_json(a) == canonical_json(b)


def _normalized(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


# --------------------------------------------------------------------------- #
# claim tipizzati (LBP2 §8)
# --------------------------------------------------------------------------- #


class ClaimRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"


@dataclass(frozen=True)
class NumericClaim:
    operation: str
    arguments: tuple[str, ...]
    subject_id: str
    value: str | Decimal | int | float
    unit: str
    precision: int
    rounding_mode: str = "truncation"
    evidence_ref: str = ""

    def __post_init__(self) -> None:
        # fallisce subito su un valore non dichiarabile, invece che in verifica
        decimal_digits(self.value)


@dataclass(frozen=True)
class DocumentClaim:
    document_hash: str
    document_version: str
    location: str
    quoted_span: str
    claim_relation: ClaimRelation


class ClaimCode(str, Enum):
    CLAIM_OK = "claim_ok"
    NO_TOOL_EVIDENCE = "no_tool_evidence"
    MODEL_VALUE_MISSING = "model_value_missing"
    FLOAT_FORBIDDEN = "float_forbidden"
    EVIDENCE_REF_MISMATCH = "evidence_ref_mismatch"
    VALUE_DIGIT_MISMATCH = "value_digit_mismatch"
    SUBJECT_MISSING = "subject_missing"
    DOCUMENT_HASH_MISMATCH = "document_hash_mismatch"
    QUOTED_SPAN_MISSING = "quoted_span_missing"


@dataclass(frozen=True)
class ClaimVerdict:
    ok: bool
    code: ClaimCode
    message: str = ""

    @classmethod
    def pass_(cls, message: str = "") -> "ClaimVerdict":
        return cls(True, ClaimCode.CLAIM_OK, message or "claim verificato")

    @classmethod
    def fail(cls, code: ClaimCode, message: str) -> "ClaimVerdict":
        return cls(False, code, message)


# --------------------------------------------------------------------------- #
# verifica dei claim
# --------------------------------------------------------------------------- #


def evidence_primary_ref(evidence: Mapping[str, Any]) -> str:
    return canonical_payload_hash(evidence)


def _evidence_refs(evidence: Mapping[str, Any]) -> tuple[str, ...]:
    """Riferimenti: primario = canonical_payload_hash dell'evidenza; legacy =
    stdout_hash dentro `machine` (schema di matematica/evidenza)."""
    machine = evidence.get("machine") or {}
    legacy = str(machine.get("stdout_hash", ""))
    return tuple(dict.fromkeys((evidence_primary_ref(evidence), legacy)))


def _expected_values(fact: Mapping[str, Any]) -> list[str]:
    """Cifre attese in forma stringa, dalla schema TRU di matematica
    (`expected` = lista di dict {label, value, float}); tollera anche stringhe."""
    out: list[str] = []
    for item in fact.get("expected") or []:
        if isinstance(item, dict):
            out.append(str(item["value"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def check_numeric_claim(claim: NumericClaim,
                        evidence: Mapping[str, Any] | None) -> ClaimVerdict:
    """Collega il claim alla sua evidenza ed esamina le cifre dichiarate.

    Assioni della barriera:
      1) senza evidenza (o senza `fact`) => NO TOOL CLAIM, il claim e' respinto;
      2) `evidence_ref` deve nominare l'evidenza: `canonical_payload_hash`
         (primario) oppure il `stdout_hash` legacy di matematica;
      3) il valore dichiarato deve essere un PREFISSO delle cifre
         dell'evidenza: troncamento ok, alterazione no;
      4) `rounding_mode="exact"` pretende che il claim non tagli cifre che
         l'evidenza possiede.
    """
    if evidence is None or not evidence.get("fact"):
        return ClaimVerdict.fail(
            ClaimCode.NO_TOOL_EVIDENCE, "no tool evidence => no tool claim")

    if claim.evidence_ref not in _evidence_refs(evidence):
        return ClaimVerdict.fail(
            ClaimCode.EVIDENCE_REF_MISMATCH,
            f"evidence_ref {claim.evidence_ref!r} non collega questa evidenza "
            f"(ref primario: {PRIMARY_HASH_FIELD})")

    if not claim.subject_id:
        return ClaimVerdict.fail(
            ClaimCode.SUBJECT_MISSING,
            "subject_id obbligatorio: l'oggetto si distingue per identita', "
            "non contando cifre nel testo")

    expected = _expected_values(evidence["fact"])
    if not expected:
        return ClaimVerdict.fail(
            ClaimCode.NO_TOOL_EVIDENCE, "fact senza cifre attese")

    expected_s = expected[0]
    if not _digits_are_prefix(str(claim.value), expected_s, claim.precision):
        return ClaimVerdict.fail(
            ClaimCode.VALUE_DIGIT_MISMATCH,
            f"cifre alterate: {claim.value} non e' prefisso corretto di "
            f"{expected_s[: claim.precision + 16]}...")

    if claim.rounding_mode == "exact":
        _ei, e_fp = _split_digits(decimal_digits(claim.value))
        _x_i, x_fp = _split_digits(expected_s)
        if len(e_fp) < len(x_fp):
            return ClaimVerdict.fail(
                ClaimCode.VALUE_DIGIT_MISMATCH,
                "rounding exact ma il claim taglia cifre che l'evidenza possiede")

    return ClaimVerdict.pass_(
        f"{claim.subject_id} verificato su {PRIMARY_HASH_FIELD}")


def check_document_claim(claim: DocumentClaim,
                         document_bytes: bytes) -> ClaimVerdict:
    """Livello 2: il claim documentale aggancia una fonte e una versione.

    `document_hash` e' la canonical_payload_hash dei byte forniti (verificata
    qui, non dichiarata). `quoted_span` deve comparire letterale nel documento.
    """
    actual = transport_bytes_hash(document_bytes)
    if claim.document_hash and actual != claim.document_hash:
        return ClaimVerdict.fail(
            ClaimCode.DOCUMENT_HASH_MISMATCH,
            f"document_hash {claim.document_hash} != sha256 dei byte forniti")
    text = document_bytes.decode("utf-8", errors="replace")
    if claim.quoted_span not in text:
        return ClaimVerdict.fail(
            ClaimCode.QUOTED_SPAN_MISSING,
            f"quoted_span {claim.quoted_span!r} assente dal documento")
    return ClaimVerdict.pass_(
        f"documento {claim.document_hash[:16]} versione {claim.document_version}")


# --------------------------------------------------------------------------- #
# prosa dichiarativa (LBP2 §8.1): il VALORE sceglie la frase, mai la frase
# --------------------------------------------------------------------------- #

_ALLOWED_OUTCOME_PHRASES = ("CLAIM_VERIFICATO", "CLAIM_RESPINTO")


def declarable_phrase(claim: NumericClaim, ok: bool) -> str:
    """Frase deterministica, selezionata stabilmente dal valore strutturato."""
    value_str = f"{claim.value:.{claim.precision}f}"
    if ok:
        return (f"{claim.subject_id} @ {claim.operation}({', '.join(claim.arguments)})"
                f" = {value_str} {claim.unit} ; {_ALLOWED_OUTCOME_PHRASES[0]}"
                f" ; ref {claim.evidence_ref}")
    return (f"{claim.subject_id} @ {claim.operation} : {_ALLOWED_OUTCOME_PHRASES[1]}"
            f" ; ref {claim.evidence_ref}")


def contains_declared_outcome(prose: str, outcome: bool) -> bool:
    """La prosa libera NON dichiara l'esito: False sempre.

    Gli slot proteggono i VALORI, non le frasi: un testo può dire
    '{{passed}}' quanto vuole, non è una dichiarazione di esito.
    """
    return False


# --------------------------------------------------------------------------- #
# confronto cifre: prefisso corretto (troncamento ok, alterazione no)
# --------------------------------------------------------------------------- #


def _split_digits(s: str) -> tuple[str, str]:
    ip, _, fp = s.partition(".")
    return ip.lstrip("-"), fp


def decimal_digits(value: Any) -> str:
    """Cifre decimali ESATTE del valore, senza mai passare da un float binario.

    `float` e' ammesso per compatibilita': `repr()` da' la rappresentazione
    decimale piu' corta che ritorna allo stesso float, cioe' le cifre che il
    chiamante ha scritto — non l'espansione binaria. Oltre ~17 cifre
    significative un float non PUO' portare la precisione: per i 40 decimali
    del CalcKernel il valore va dichiarato come stringa o `Decimal`.
    """
    if isinstance(value, bool):
        raise TypeError("bool non e' un valore numerico dichiarabile")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    s = str(value).strip()
    if not s:
        raise ValueError("valore numerico vuoto")
    return format(Decimal(s), "f")      # valida e normalizza (niente 1e-05)


def _sign_of(s: str) -> str:
    return "-" if s.lstrip().startswith("-") else "+"


def _digits_are_prefix(declared: Any, expected: str, precision: int) -> bool:
    """Le cifre dichiarate sono un prefisso corretto di quelle attese.

    Confronto STRINGA contro STRINGA: `float()` non compare nel percorso di
    verifica. Prima ci passava, e l'espansione binaria corrompeva le cifre
    (`float("143.1118")` -> `143.11179999999998...`, troncato a 4 decimali da
    `1117`): ~50% dei claim FEDELI veniva respinto, con la suite verde perche'
    le fixture cadevano dal lato favorevole dell'errore di rappresentazione.

    Dichiarare `precision = P` significa affermare le prime P cifre decimali.
    Un valore piu' corto NON e' sotto-specificato: `42.5` vale esattamente
    `42.5000`, quindi le cifre implicite sono zeri e vanno confrontate come
    tali. L'evidenza, invece, deve possedere almeno P cifre: dichiararne piu'
    di quante ne esistano e' un claim falso.
    """
    if precision <= 0:
        return False
    try:
        dec_s = decimal_digits(declared)
    except (ValueError, TypeError, ArithmeticError, InvalidOperation):
        return False

    if _sign_of(dec_s) != _sign_of(expected):
        return False

    i_dec, f_dec = _split_digits(expected)
    i_exp, f_exp = _split_digits(dec_s)
    if i_dec != i_exp:
        return False
    if len(f_dec) < precision:
        return False
    return f_exp.ljust(precision, "0")[:precision] == f_dec[:precision]