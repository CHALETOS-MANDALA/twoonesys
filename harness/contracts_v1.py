"""CASCADE - Integrazione: contratti System One, v1 (LBP2_CONTRATTI_V1).

L'invariante del documento (par. 0): il runtime deve poter distinguere, per
ogni risultato, cio' che ha **verificato**, cio' che ha **stimato**, cio' che
ha **autorizzato** e cio' che e' realmente **accaduto**. Quattro confini, mai
collassati l'uno nell'altro: una prova matematica non e' un permesso, una
probabilita' alta non supera un divieto.

   DATO          DECISIONE          AUTORIZZAZIONE        ESECUZIONE
   valido?       corretta?           consentita?            riuscita?
     |               |                    |                    |
   Assessment    CalibrationPolicy    Authorization      ExecutionResult

Questo modulo e' UN'INTEGRAZIONE, non un refactor: non tocca ne'
neurosymbolic_guard.py ne' pipeline.py ne' contracts.py (da cui riusa
sha256_hex/canonical_json per il contract_digest). Copre il passo 1 della
migrazione: la separazione dei confini esiste PRIMA di qualunque lavoro di
calibrazione, perche' e' un difetto che esiste oggi.

Disciplina dei tipi (par. 12): CalibratedEstimate NON e' un numero con cui si
fa aritmetica — nessun __gt__, __add__, __float__. Il confronto passa da
un'unica API di policy che verifica compatibilita' (stesso target_event,
calibratore applicabile, valore in range). NewType su float non garantisce
nulla (provato con mypy --strict nei doc): serve un wrapper opaco.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeAlias, TypeVar

from .contracts import sha256_hex

# --------------------------------------------------------------------------- #
# Result[T, E] — l'errore tipizzato come valore, non come eccezione
# --------------------------------------------------------------------------- #
# Par. 11: TaskGroup cancella le altre task quando una fallisce. Per avere
# risultati parziali gli errori ATTESI dei produttori diventano valori
# tipizzati dentro ciascuna task: questo tipo e' cio' che rende possibile il
# parziale. unwrap() solleva solo per errori di programmazione (asserzione),
# mai per esiti attesi.

S = TypeVar("S")
F = TypeVar("F")


class UnwrapError(ValueError):
    """Sollevata solo quando si fa unwrap() su un ramo errato: bug di chi chiama."""


@dataclass(frozen=True)
class Result(Generic[S, F]):
    """Un valore tipizzato O un errore tipizzato, mai entrambi."""
    _ok: S | None = None
    _err: F | None = None

    def __post_init__(self) -> None:
        if (self._ok is None) == (self._err is None):
            raise ValueError("Result deve contenere esattamente un ramo (ok o err)")

    @classmethod
    def ok(cls, value: S) -> "Result[S, F]":
        return cls(_ok=value)

    @classmethod
    def err(cls, error: F) -> "Result[S, F]":
        return cls(_err=error)

    @property
    def is_ok(self) -> bool:
        return self._err is None

    @property
    def is_err(self) -> bool:
        return self._err is not None

    @property
    def value(self) -> S | None:
        return self._ok

    @property
    def error(self) -> F | None:
        return self._err

    def unwrap(self) -> S:
        if self._err is not None:
            raise UnwrapError(f"unwrap() su un ramo err: {self._err!r}")
        return self._ok  # type: ignore[return-value]

    def unwrap_or(self, default: S) -> S:
        return self._ok if self._err is None else default

    def map(self, fn) -> "Result[S, F]":
        if self._err is None:
            return Result.ok(fn(self._ok))
        return self


# --------------------------------------------------------------------------- #
# Che cosa SO                     (Assessment: Verified | Estimated | Insufficient)
# --------------------------------------------------------------------------- #

EventId: TypeAlias = str
"""Identifica l'evento osservabile a cui si riferisce una stima/verifica."""

VerifierRef: TypeAlias = str
"""Riferimento al verificatore (kernel, z3, barriera evidenza, test, ...)."""


@dataclass(frozen=True)
class Verified:
    """Una proposizione verificata, SOTTO quali assunzioni e da quale verificatore.

    Non dice nulla sull'autorizzazione a eseguire: `Verified("Re(rho_50)=1/2",
    True, ...)` non autorizza a scrivere un file.
    """
    proposition: str
    value: object
    evidence_ref: str
    assumptions: tuple[str, ...]
    verifier_ref: VerifierRef


@dataclass(frozen=True)
class Estimated:
    """Una stima riferita a UN preciso evento osservabile, non 'certo' generico.

    La stima porta il contract_digest del calibratore che l'ha prodotta: un
    digest diverso la rende non applicabile (par. 3.2).
    """
    target_event: EventId
    estimate: "CalibratedEstimate"
    calibration_ref: str


@dataclass(frozen=True)
class Insufficient:
    """Non c'e' abbastanza evidenza per una verifica o una stima."""
    reason: str


Assessment: TypeAlias = Verified | Estimated | Insufficient


# --------------------------------------------------------------------------- #
# Che cosa POSSO fare             (Authorization: Permit | Deny | Review)
# --------------------------------------------------------------------------- #

ActionClass: TypeAlias = str
"""Classe d'azione: es. 'read', 'write:disk', 'azioni:esegui', 'transfer'."""


@dataclass(frozen=True)
class Permit:
    """Permesso LIMITATO per una specifica azione e specifici argomenti (one-shot).

    E' il contratto che in SIX-IDE esiste gia' come ActionGrant a tre facce
    (grant.rs <-> grant.ts <-> gateway/granting.py): registro degli emittenti,
    consumo one-shot, confronto profondo esatto dei parametri. Manca solo il
    ricontrollo ATOMICO delle precondizioni al momento dell'uso (anti-TOCTOU),
    che arriva col gate (passo 2).
    """
    action_digest: str
    arguments_digest: str
    scope: tuple[str, ...]
    preconditions: tuple[str, ...]
    expires_at: float          # epoch; il grant non vale oltre questo istante
    grant_id: str              # identificatore anti-riuso
    subject_id: str            # identita' del soggetto autorizzato


@dataclass(frozen=True)
class Deny:
    reason: str


@dataclass(frozen=True)
class Review:
    reason: str


Authorization: TypeAlias = Permit | Deny | Review


# --------------------------------------------------------------------------- #
# Che cosa E' SUCCESSO           (ExecutionResult: Succeeded | Failed | Indeterminate)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Succeeded:
    receipt: str
    observed_postconditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Failed:
    error: str


@dataclass(frozen=True)
class Indeterminate:
    """Un timeout NON dimostra un fallimento: lo stato e' ignoto e va riconciliato.

    Se l'esecutore perde la risposta dopo che l'azione potrebbe essere
    avvenuta, questo non e' `Failed`: e' uno stato da riconciliare (par. 1.1).
    """
    reconciliation_ref: str


ExecutionResult: TypeAlias = Succeeded | Failed | Indeterminate


# --------------------------------------------------------------------------- #
# Tipi opachi con disciplina (§6 e §12 del contratto)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CalibratedEstimate:
    """Una stima calibrata: NON un numero con cui si fa aritmetica.

    Niente __gt__/__add__/__float__: il confronto passa da CalibrationPolicy.
    Il valore e' validato nel costruttore (finito, in [0,1]). Il digest lega
    la stima al calibratore che l'ha prodotta.
    """
    value: float
    target_event: EventId
    contract_digest: str

    def __post_init__(self) -> None:
        v = float(self.value)
        if not math.isfinite(v) or not (0.0 <= v <= 1.0):
            raise ValueError(f"CalibratedEstimate fuori range: {self.value!r}")
        if not self.contract_digest:
            raise ValueError("CalibratedEstimate senza contract_digest: calibratore ignoto")


@dataclass(frozen=True)
class ProbabilityThreshold:
    """Una soglia legata a UN evento e a UNA classe d'azione, mai nuda."""
    value: float
    target_event: EventId
    action_class: ActionClass

    def __post_init__(self) -> None:
        v = float(self.value)
        if not math.isfinite(v) or not (0.0 <= v <= 1.0):
            raise ValueError(f"ProbabilityThreshold fuori range: {self.value!r}")


@dataclass(frozen=True)
class CalibrationPolicy:
    """L'unica API che confronta una stima con una soglia.

    Verifica esplicitamente: stesso target_event, calibratore applicabile
    (digest registrato), soglia per la stessa classe d'azione. Un digest non
    registrato rende la stima NON applicabile: il gate tornerebbe
    `Insufficient`, mai una probabilita' vecchia.
    """
    target_event: EventId
    action_class: ActionClass
    applicable_digests: frozenset[str] = frozenset()

    def applicable(self, estimate: CalibratedEstimate) -> bool:
        if estimate.target_event != self.target_event:
            return False
        if self.applicable_digests and estimate.contract_digest not in self.applicable_digests:
            return False
        return True

    def accepts(self, estimate: CalibratedEstimate,
                threshold: ProbabilityThreshold) -> bool:
        """Risponde solo a 'la stima supera la soglia?'. NON e' un'autorizzazione.

        Un `True` qui non concede nulla: va SEMPRE composto con un
        Authorization esplicito a valle, nel gate (passo 2). Una probabilita'
        alta non supera un divieto.
        """
        if threshold.target_event != self.target_event:
            return False
        if threshold.action_class != self.action_class:
            return False
        if not self.applicable(estimate):
            return False
        return estimate.value >= threshold.value


# --------------------------------------------------------------------------- #
# Supporto ad osservabili definibili (§6: la terna epistemica e' ritirata)
# --------------------------------------------------------------------------- #


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceCoverage:
    state: str          # satisfied_requirements | missing_requirements | conflicting_requirements


@dataclass(frozen=True)
class CalibrationSupport:
    sample_count: int
    evaluation_ref: str
    applicability_status: str   # pending | valid | superseded | not_applicable


@dataclass(frozen=True)
class OODSignal:
    raw_score: float
    detector_version: str
    threshold_version: str


# --------------------------------------------------------------------------- #
# contract_digest (§3.2)
# --------------------------------------------------------------------------- #


def contract_digest(**components: object) -> str:
    """Un digest dalla configurazione EFFETTIVA, non da campi trascritti a mano.

    Cambia una qualunque componente -> digest diverso -> le stime portate da
    quel digest non sono piu' applicabili e il gate torna Insufficient. Un
    dimenticatoio e' impossibile perche' il digest si calcola dalla chiave
    realmente passata / effettivamente in uso.
    """
    return sha256_hex(dict(sorted(components.items())))


# --------------------------------------------------------------------------- #
# BackendCaps (§P7 / §7 contratti)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BackendCaps:
    """Cio' che un backend DICHIARA di saper fare; l'harness degrada da solo."""
    name: str
    grammar: bool = False          # decoding vincolato / grammatica
    json_schema: bool = False      # JSON mode con schema
    tool_call: bool = False        # function calling tipizzato
    logprobs: bool = False         # log-probabilita' dei token
    batch: bool = False            # piu' campioni in una chiamata
    max_cardinality: int = 1       # massima cardinalita' dell'enum decisionale

    def __post_init__(self) -> None:
        if self.max_cardinality < 1:
            raise ValueError("max_cardinality deve essere >= 1")