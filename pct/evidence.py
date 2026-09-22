"""Il contratto dell'evidenza -- l'unico punto di variazione fra i bracci.

Regola dura della carta (rev. 3 §7): un provider NON restituisce mai un'azione.
Restituisce stime, supporto ed eventi rari. Decide la policy, che e' una sola.

Le guardie qui sotto sono ATTIVE, non decorative: l'audit ha trovato che la
versione precedente cercava chiavi testuali dentro un dizionario a chiavi intere,
quindi non poteva scattare mai. Ora si controllano i tipi e i nomi dei campi.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Mapping, Protocol, Sequence

# nomi che, comparendo in un'evidenza, significherebbero che l'indice ha deciso
NOMI_DI_DECISIONE = ("action", "chosen", "decision", "best", "choice", "azione")
# nomi che significherebbero che l'indice ha ordinato
NOMI_DI_RANKING = ("score", "rank", "ranking", "recency", "priority", "weight")


class Status(str, Enum):
    OK = "OK"
    NO_EVIDENCE = "NO_EVIDENCE"   # supporto insufficiente: ESS sotto soglia
    UNKNOWN = "UNKNOWN"           # nessun dato e nessun modo lecito di ottenerlo


@dataclass(frozen=True)
class Conditions:
    """Condizioni osservabili PRIMA della decisione (carta §4.2: mai post-azione)."""

    d: int
    e: int
    t: int


#: le uniche variabili ammesse come condizione. Una variabile osservata DOPO
#: l'azione non entra mai: e' un collider e fabbricherebbe un effetto inesistente.
CONDIZIONI_AMMESSE: tuple[str, ...] = ("d", "e")
CONDIZIONI_VIETATE: tuple[str, ...] = (
    "outcome", "success", "magnitude", "action", "reward", "prop", "t")


def assert_pre_decision(nome: str) -> None:
    """Guardia collider viva: rifiuta una condizione non pre-decisione."""
    if nome in CONDIZIONI_VIETATE:
        raise ValueError(
            f"'{nome}' non e' osservabile prima della decisione: "
            "una variabile post-azione non puo' entrare nella state_key")
    if nome not in CONDIZIONI_AMMESSE:
        raise ValueError(f"condizione non dichiarata: '{nome}'")


@dataclass(frozen=True)
class ActionEvidence:
    value_hat: float
    ess: float
    n: int
    std_err: float


@dataclass(frozen=True)
class RareEvent:
    action: int
    magnitude: float
    conditions: Conditions


@dataclass(frozen=True)
class Evidence:
    per_action: Mapping[int, ActionEvidence]
    rare_events: tuple[RareEvent, ...] = ()
    status: Status = Status.OK
    unknown_actions: tuple[int, ...] = ()
    conditioning: str = ""

    def __post_init__(self) -> None:
        # 1. le chiavi devono essere identificatori di azione, non nomi
        for k in self.per_action:
            if isinstance(k, bool) or not isinstance(k, int):
                raise TypeError(
                    "l'evidenza non puo' contenere un'azione scelta: "
                    f"chiave non intera {k!r}")
            if k < 0:
                raise TypeError(f"identificatore di azione non valido: {k!r}")
        # 2. la struttura non puo' esporre campi di decisione o di ranking
        nomi = {f.name for f in fields(self)}
        vietati = nomi & (set(NOMI_DI_DECISIONE) | set(NOMI_DI_RANKING))
        if vietati:  # pragma: no cover - scatta solo se qualcuno modifica la classe
            raise TypeError(f"campo vietato nell'evidenza: {sorted(vietati)}")


class EvidenceProvider(Protocol):
    name: str

    def query(self, state: int, eligible: Sequence[int],
              conditions: Conditions) -> Evidence: ...


def empty_if_starved(per_action: dict[int, ActionEvidence], ess_min: float,
                     rare: tuple[RareEvent, ...], conditioning: str,
                     unknown: tuple[int, ...] = ()) -> Evidence:
    """NO_EVIDENCE se nessuna azione raggiunge il supporto minimo.

    UNKNOWN se, in piu', le azioni senza dati non sono nemmeno esplorabili:
    quel vuoto non si colmera' mai, ed e' il limite epistemologico della carta
    §7.1 -- il sistema deve poterlo dichiarare invece di fingere una stima.
    """
    usable = {a: ev for a, ev in per_action.items() if ev.ess >= ess_min}
    if usable:
        return Evidence(per_action=usable, rare_events=rare, status=Status.OK,
                        unknown_actions=unknown, conditioning=conditioning)
    stato = Status.UNKNOWN if unknown and not per_action else Status.NO_EVIDENCE
    return Evidence(per_action={}, rare_events=rare, status=stato,
                    unknown_actions=unknown, conditioning=conditioning)
