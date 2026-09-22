"""CASCADE - Passo 7: la DISCIPLINA di registrare gli esiti (persistente).

L'audit (AUDIT_FINALE_2026-09-17): "il pezzo mancante e' un modulo da
centoventi righe, piu' la disciplina di registrare gli esiti". I misuratori
(ReliabilityMeter) e l'escalation in ombra (ShadowEscalation) sono IN
MEMORIA: al riavvio del processo la storia degli esiti sparisce e la curva
di calibrazione ricomincia da zero. Questo modulo E' la disciplina: ogni
esito (con la confidenza grezza e quella calibrata) viene APPESO a un JSONL
sul disco; al riavvio la log si ricarica e la curva si RICOSTRUISCE identica.

Regole di onesta':
* OUTCOME INDETERMINATO (risposta persa) NON alimenta mai il misuratore:
  `outcome=None` viene registrato ma non entra in `replay_into` (uno stato
  ignoto non e' ne' successo ne' fallimento, par. 1.1 di LBP2_CONTRATTI_V1).
* La confidenza grezza e quella calibrata viaggiano insieme: cosi' la log
  permette di ri-collaudare la calibrazione a posteriori (audit), non solo
  di usarla.
* Le righe malformate in lettura NON vengono buttate via in silenzio:
  vengono contate e riportate in `load()`; la log continua a crescere ma la
  metrica espone `bad_lines`.
* Dedup per request_id: se lo stesso caso viene conciliato piu' volte
  (es. dopo un Indeterminate si riallinea l'esito), vince l'ULTIMA riga.

Dipendenze: stdlib. Nessuna modifica ai moduli esistenti.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .reliability import ReliabilityMeter


@dataclass(frozen=True)
class OutcomeRecord:
    """Un caso del circuito chiuso, registrato a posteriori.

    `approved=True` significa che System One/Two ha DAVVERO eseguito con
    esito Succeeded (mai un "permesso" da solo). `outcome=None` = ancora
    ignoto (Indeterminate da riconciliare): non conta come successo NE'
    come fallimento.
    """
    request_id: str
    action: str                           # categoria di azione (es. "file_write")
    raw_confidence: float
    action_chosen: str | None = None      # identita' del braccio scelto (per IPS/dr)
    measured_p: float | None = None       # None = nessuna misura (cold start), mai un numero
    escalated: bool = False
    approved: bool = False                # gate di autorizzazione ha passato? (non outcome)
    outcome: bool | None = None           # esecuzione: True/False/None (Indeterminate)
    touched: float = 0.0
    version: int = 2

    # --- campi richiesti dalla verifica indipendente 2026-09-18 ----------- #
    # Vanno registrati QUANDO si decide: la propensione non e' recuperabile a
    # posteriori, e senza di essa non si puo' stimare offline una politica mai
    # eseguita (IPS / doubly-robust) ne' togliere la distorsione dei dati di
    # esplorazione.
    selection_probability: float | None = None   # pi(azione scelta | stato)
    contract_digest: str = ""                    # invalida il calibratore al cambio
    label_source: str | None = None              # chi ha stabilito l'esito

    LABEL_SOURCES = ("mechanical", "human", "behavioral")

    def __post_init__(self) -> None:
        if not str(self.request_id).strip():
            raise ValueError("OutcomeRecord: request_id vuoto")
        c = float(self.raw_confidence)
        if not (0.0 <= c <= 1.0):
            raise ValueError(f"OutcomeRecord: raw_confidence fuori range: {c!r}")
        object.__setattr__(self, "raw_confidence", c)
        if self.measured_p is not None:
            m = float(self.measured_p)
            if not (0.0 <= m <= 1.0):
                raise ValueError(f"OutcomeRecord: measured_p fuori range: {m!r}")
            object.__setattr__(self, "measured_p", m)
        if self.outcome is not None and not isinstance(self.outcome, bool):
            raise ValueError(
                f"OutcomeRecord: outcome deve essere bool o None, non {self.outcome!r}")
        if self.selection_probability is not None:
            p = float(self.selection_probability)
            # zero e' vietato: un'azione con propensione 0 rende infinito il
            # peso IPS. Se e' stata scelta, la sua probabilita' non era 0.
            if not (0.0 < p <= 1.0):
                raise ValueError(
                    f"OutcomeRecord: selection_probability deve stare in (0,1]: {p!r}")
            object.__setattr__(self, "selection_probability", p)
        if self.label_source is not None and self.label_source not in self.LABEL_SOURCES:
            raise ValueError(
                f"OutcomeRecord: label_source {self.label_source!r} fuori da "
                f"{self.LABEL_SOURCES}")

    def to_json(self) -> str:
        return json.dumps(vars(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "OutcomeRecord":
        data = json.loads(line)
        allowed = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)


class OutcomeLog:
    """Registro append-only (JSONL) degli esiti, ricostruibile al riavvio.

    `path=None` (default nei test): solo in memoria, nessun disco. Con un
    percorso, la prima `record()` crea la directory se serve e appende una
    riga per caso; `load()` rilegge il file esistente e deduplica per
    request_id (vince l'ultima). I record malformati sono contati, non
    fatti sparire.
    """

    APPEND_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_APPEND

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path is not None else None
        self._records: dict[str, OutcomeRecord] = {}
        self.bad_lines = 0

    # ------------------------------------------------------------------ #
    # scrittura
    # ------------------------------------------------------------------ #
    def record(self, rec: OutcomeRecord) -> "OutcomeLog":
        self._records[rec.request_id] = rec
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(rec.to_json() + "\n")
        return self

    # ------------------------------------------------------------------ #
    # lettura / ricostruzione (il "restart")
    # ------------------------------------------------------------------ #
    def load(self) -> "OutcomeLog":
        """Rilegge il file esistente (se c'e'), dedup per request_id."""
        if self.path is None or not self.path.exists():
            return self
        bad = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = OutcomeRecord.from_json(line)
            except (ValueError, json.JSONDecodeError, TypeError):
                bad += 1
                continue
            self._records[rec.request_id] = rec    # vince l'ULTIMA
        self.bad_lines += bad
        return self

    # ------------------------------------------------------------------ #
    # accesso
    # ------------------------------------------------------------------ #
    def records(self) -> tuple[OutcomeRecord, ...]:
        """In ordine stabile di inserimento (dict preserve-order)."""
        return tuple(self._records.values())

    def settled(self) -> Iterator[tuple[float, bool]]:
        """Solo gli esiti NOTI: (confidenza grezza, esito). Mai un `None`."""
        for rec in self._records.values():
            if rec.outcome is not None:
                yield rec.raw_confidence, bool(rec.outcome)

    @property
    def size(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------ #
    # ricostruzione del misuratore (la curva identica dopo il riavvio)
    # ------------------------------------------------------------------ #
    def replay_into(self, meter: ReliabilityMeter) -> ReliabilityMeter:
        """Ricostruisce la curva di calibrazione dagli esiti registrati."""
        settled = list(self.settled())
        if settled:
            confs = [c for c, _ in settled]
            outs = [o for _, o in settled]
            meter.record_many(confs, outs).fit()
        return meter

    # ------------------------------------------------------------------ #
    # metrica onesta (mai inventata)
    # ------------------------------------------------------------------ #
    def metrics(self) -> dict:
        """Contatori e medie; niente numeri quando non c'e' storia."""
        n = len(self._records)
        if n == 0:
            return {"n": 0, "settled": 0, "approved": 0,
                    "with_propensity": 0, "with_label_source": 0,
                    "off_policy_ready": False,
                    "success_rate": None, "mean_raw_confidence": None,
                    "bad_lines": self.bad_lines}
        settled = [(r.raw_confidence, r.outcome) for r in self._records.values()
                   if r.outcome is not None]
        n_ok = sum(1 for r in self._records.values() if r.outcome is True)
        rec = self._records.values()
        return {
            "n": n,
            "settled": len(settled),
            "approved": sum(1 for r in rec if r.approved),
            # visibilita' delle lacune: cosa NON si potra' fare con questa log
            "with_propensity": sum(1 for r in rec if r.selection_probability is not None),
            "with_label_source": sum(1 for r in rec if r.label_source is not None),
            "off_policy_ready": all(
                r.selection_probability is not None for r in rec) if n else False,
            "success_rate": (n_ok / len(settled) if settled else None),
            "mean_raw_confidence": (
                sum(c for c, _ in settled) / len(settled) if settled else None),
            "bad_lines": self.bad_lines,
        }


def replay_all(path: str | os.PathLike | None,
               meter: ReliabilityMeter | None = None) -> tuple[OutcomeLog, ReliabilityMeter]:
    """Riapre la log e ricostruisce (log, meter) — il gesto del riavvio."""
    log = OutcomeLog(path).load()
    meter = meter or ReliabilityMeter()
    log.replay_into(meter)
    return log, meter