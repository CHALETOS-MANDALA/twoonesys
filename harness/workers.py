"""CASCADE - Passo 4: worker RESIDENTI (in-process), grafo di dipendenza.

Le integrazioni non girano piu' a subprocess per chiamata: PRISM (punteggio
di pertinenza) e CalcKernel (calcolo ad alta precisione) sono ospitati NEL
PROCESSO di CASCADE. I backend si importano SOTTO SFORZO, mai al modulo:
se il pacchetto non e' importabile il worker resta BLOCKED e non inventa
risultati (nessun fabbricato).

Grafo di dipendenza esplicito (vedi DEPENDENCY_GRAPH):
    docs.retrieve -> prism.relevance -> calc.kernel -> claim.barrier

Formato evidenza: IDENTICO a matematica/evidenza/evidence.py
(intent/params/immutable/machine/fact). Qui e' riprodotto senza importare
quella cartella, cosi' la barriera del passo 3 (e `matematica/barrier.verify`)
possono consumare lo stesso oggetto.
"""

from __future__ import annotations

import importlib
import os
import sys
import httpx
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from cascade.claim_barrier import (
    ClaimCode,
    ClaimVerdict,
    NumericClaim,
    canonical_payload_hash,
    check_numeric_claim,
)

# --------------------------------------------------------------------------- #
# identita' dei worker nel grafo
# --------------------------------------------------------------------------- #

WORKER_DOCS = "docs.retrieve"          # documenti recuperati (input del resto)
WORKER_PRISM = "prism.relevance"       # PRISM: pertinenza [0,1] dei doc
WORKER_CALC = "calc.kernel"            # CalcKernel: evidenza numerica/outcome
WORKER_BARRIER = "claim.barrier"       # barriera claim <-> evidenza (passo 3)
WORKER_KIARNEL = "kiarnel.verify"      # KIARNEL: verifica operativa esterna

DEPENDENCY_GRAPH: dict[str, frozenset[str]] = {
    WORKER_DOCS: frozenset(),
    WORKER_PRISM: frozenset({WORKER_DOCS}),
    WORKER_CALC: frozenset(),
    WORKER_BARRIER: frozenset({WORKER_CALC}),
    WORKER_KIARNEL: frozenset(),
}

_DEFAULT_KERNEL_DIR = (
    "C:\\Users\\andre\\Desktop\\matematica\\kernel"
)


def validate_graph() -> None:
    """La DAG deve essere conosciuta: ogni dipendenza e' un worker reale."""
    unknown = {d for w, deps in DEPENDENCY_GRAPH.items() for d in deps
               if d not in DEPENDENCY_GRAPH}
    if unknown:
        raise ValueError(f"dipendenze sconosciute: {unknown}")


def upstream(kind: str) -> tuple[str, ...]:
    """Ordine topologico dei worker che devono precedere `kind` (livelli)."""
    validate_graph()
    seen: set[str] = set()
    order: list[str] = []

    def visit(k: str) -> None:
        if k in seen:
            return
        seen.add(k)
        for dep in sorted(DEPENDENCY_GRAPH.get(k, frozenset())):
            visit(dep)
        order.append(k)

    visit(kind)
    return tuple(order)


# --------------------------------------------------------------------------- #
# stato dei backend
# --------------------------------------------------------------------------- #


class WorkerStatus(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"          # backend non registrato / non importabile
    UNAVAILABLE = "unavailable"  # chiamata fallita con errore
    ERROR = "error"


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    status: WorkerStatus
    payload: Any = None
    message: str = ""


@dataclass(frozen=True)
class ChainReport:
    stages: tuple[WorkerResult, ...]
    verdict: ClaimVerdict
    subject_id: str = ""
    claim: NumericClaim | None = None

    @property
    def all_ok(self) -> bool:
        return all(s.status is WorkerStatus.OK for s in self.stages)


class BackendUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# registrazione backend (thunk: import sotto sforzo alla chiamata)
# --------------------------------------------------------------------------- #

_BACKENDS: dict[str, Callable[..., Any]] = {}


def register_backend(name: str, fn: Callable[..., Any]) -> None:
    if name not in DEPENDENCY_GRAPH:
        raise ValueError(f"worker sconosciuto: {name}")
    _BACKENDS[name] = fn


def get_backend(name: str) -> Callable[..., Any] | None:
    return _BACKENDS.get(name)


def backend_status(name: str) -> WorkerStatus:
    return WorkerStatus.OK if name in _BACKENDS else WorkerStatus.BLOCKED


def _load(module: str, path_hint: str | None = None):
    """Import sotto sforzo. Ritorna il modulo o alza BackendUnavailable."""
    try:
        if path_hint:
            if not os.path.isdir(path_hint):
                raise BackendUnavailable(
                    f"cartella configurata inesistente: {path_hint}")
            sys.path.append(path_hint)
        return importlib.import_module(module)
    except BackendUnavailable:
        raise
    except Exception as exc:
        raise BackendUnavailable(
            f"{module} non importabile in-process") from exc


# --------------------------------------------------------------------------- #
# PRISM residente: pertinenza dei documenti recuperati
# --------------------------------------------------------------------------- #


def prism_relevance(query: str, docs: list[str], top: int = 1) -> list[tuple[int, float]]:
    """Punteggio di PRISM ([0,1], kernel calibrato + IDF sul corpus).

    I documenti sono gia' recuperati (dipendenza WORKER_DOCS): qui si
    classifica, non si recupera nulla.
    """
    prism_dir = os.environ.get("CASCADE_PRISM_PATH")
    geo = _load("prism.geometry", path_hint=prism_dir)
    probe = geo.QueryProbe.build(query)
    scored = [
        (i, probe.relevance(doc, corpus=docs))
        for i, doc in enumerate(docs)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:max(top, 0)]


# --------------------------------------------------------------------------- #
# CalcKernel residente: evidenza in schema matematica, senza subprocess
# --------------------------------------------------------------------------- #


def _machine_record(tool_args: list[str], payload: dict) -> dict[str, Any]:
    import hashlib
    import json
    stdout = json.dumps(payload, indent=2, ensure_ascii=False)
    return {
        "tool": "mathkernel.calc", "args": [str(a) for a in tool_args],
        "exit_code": 0,
        "stdout_hash": hashlib.sha256(stdout.encode("utf-8")).hexdigest()[:16],
        "parsed": payload,
    }


def calc_evidence(kind: str, **kwargs: Any) -> dict[str, Any]:
    """Esegue il CalcKernel IN-PROCESS (main.dati, zero subprocess) e
    restituisce l'evidenza nel formato identico a matematica/evidenza.

    kind ammessi: "zeron" (numerico: Im/Re) e "robin" (outcome: all_ok).
    """
    mathkernel_dir = os.environ.get("CASCADE_MATEMATICA_KERNEL") or _DEFAULT_KERNEL_DIR
    calc = _load("mathkernel.calc", path_hint=mathkernel_dir)

    if kind == "zeron":
        n = int(kwargs.get("n", 1))
        digits = int(kwargs.get("digits", 40))
        p = calc.zetazero(n, digits)
        im = str(p["Im"])
        re_ = str(p["Re"])
        machine = _machine_record(["zeron", n, digits], p)
        params = {"n": n, "digits": digits}
        expected = [
            {"label": "Im", "value": im, "float": float(im)},
            {"label": "Re", "value": re_, "float": float(re_),
             "boundary": True},
        ]
        outcome = {"on_critical_line": bool(p["on_critical_line"])}
        return _fact("zero_nth", params, machine, expected, outcome, p)

    if kind == "robin":
        nmax = int(kwargs.get("nmax", 1_000_000))
        p = calc.robin_check(nmax)
        machine = _machine_record(["robin", nmax], p)
        params = {"nmax": nmax}
        all_ok = bool(p.get("all_ok"))
        return _fact("criteria_robin", params, machine,
                     expected=[], outcome={"all_ok": all_ok}, payload=p)

    raise BackendUnavailable(f"calcolo sconosciuto: {kind}")


def kiarnel_verify(goal: str, file: str, *, execute: bool = False,
                   base_url: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Chiama KIARNEL reale e accetta solo una risposta JSON positiva.

    Il servizio puo' essere protetto da bearer token. Nessun errore HTTP,
    risposta vuota o `ok != true` viene trasformato in evidenza valida.
    """
    if not goal.strip() or not file.strip():
        raise BackendUnavailable("KIARNEL richiede goal e file")
    base = (base_url or os.environ.get("CASCADE_KIARNEL_URL")
            or "http://127.0.0.1:8023").rstrip("/")
    headers: dict[str, str] = {}
    token = (os.environ.get("KIARNEL_CLIENT_TOKEN")
             or os.environ.get("KIARNEL_TOKEN")
             or os.environ.get("GROK_TOKEN"))
    if not token:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            token_path = os.path.join(local_appdata, "Kiarnel", "auth.token")
            try:
                token = open(token_path, encoding="utf-8").read().strip()
            except OSError:
                token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"goal": goal, "file": file, "execute": bool(execute)}
    try:
        response = httpx.post(f"{base}/v1/ask", json=payload,
                              headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        raise BackendUnavailable(f"KIARNEL non disponibile: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise BackendUnavailable("KIARNEL ha rifiutato la verifica")
    return {"backend": "kiarnel", "endpoint": "/v1/ask", "request": payload,
            "response": data}


def _fact(kind: str, params: dict, machine: dict,
          expected: list[dict], outcome: dict, payload: dict) -> dict[str, Any]:
    return {
        "intent": kind, "params": params, "immutable": True,
        "machine": machine,
        "fact": {"kind": kind, "expected": expected, "outcome": outcome,
                 "payload": payload},
    }


# --------------------------------------------------------------------------- #
# catena verificata: docs -> relevance -> calc -> barrier (vertical slice)
# --------------------------------------------------------------------------- #


def parse_model_claim_value(text: str | None) -> str | None:
    """Estrae un claim tipizzato. Mai il primo numero nella prosa.

    Formati ammessi, nient'altro:
      - una riga `CLAIM_VALUE=<decimale>`
      - JSON con chiave `claim_value`
    """
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("CLAIM_VALUE="):
            value = line.split("=", 1)[1].strip()
            return value or None
    if raw.startswith("{"):
        try:
            import json
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if isinstance(data, dict) and data.get("claim_value") not in (None, ""):
            return str(data["claim_value"])
    return None


def run_verified(
    query: str,
    docs: list[str],
    *,
    calc_kind: str = "zeron",
    calc_args: Mapping[str, Any] = None,
    kiarnel: Mapping[str, Any] | None = None,
    precision: int = 10,
    backends: Mapping[str, Callable[..., Any]] | None = None,
    model_value: str | Any | None = None,
) -> ChainReport:
    """Esegue la catena: evidenza dal kernel, claim dal modello.

    Il valore del claim NON puo' nascere dalle cifre del kernel. Senza
    `model_value` (o CLAIM_VALUE tipizzato nel testo) il verdetto fallisce:
    nessuna auto-verifica, nessun float.
    """
    calc_args = dict(calc_args or {})
    get = lambda name: (backends or {}).get(name) or _BACKENDS.get(name)

    stages: list[WorkerResult] = []

    def _run(kind: str, *a: Any, **kw: Any) -> Any | None:
        fn = get(kind)
        if fn is None:
            stages.append(WorkerResult(
                kind, WorkerStatus.BLOCKED,
                message=f"backend {kind} non registrato"))
            return None
        try:
            out = fn(*a, **kw)
            stages.append(WorkerResult(kind, WorkerStatus.OK, payload=out))
            return out
        except BackendUnavailable as exc:
            stages.append(WorkerResult(
                kind, WorkerStatus.BLOCKED, message=str(exc)))
            return None
        except Exception as exc:  # noqa: BLE001
            stages.append(WorkerResult(
                kind, WorkerStatus.ERROR, message=f"{type(exc).__name__}: {exc}"))
            return None

    # docs (input implicito: i documenti sono gia' recuperati)
    stages.append(WorkerResult(WORKER_DOCS, WorkerStatus.OK,
                               message=f"{len(docs)} documenti"))

    rel = _run(WORKER_PRISM, query, docs, 1)
    if not rel:
        return ChainReport(tuple(stages),
                           ClaimVerdict.fail(
                               ClaimCode.NO_TOOL_EVIDENCE,
                               "PRISM non disponibile: nessun soggetto"),
                           subject_id="")

    top_idx, score = rel[0]
    evidence = _run(WORKER_CALC, calc_kind, **calc_args)
    if evidence is None:
        return ChainReport(tuple(stages),
                           ClaimVerdict.fail(
                               ClaimCode.NO_TOOL_EVIDENCE,
                               "CalcKernel non disponibile: nessuna evidenza"),
                           subject_id=f"doc-{top_idx}")

    expected_list = evidence.get("fact", {}).get("expected") or []
    if not expected_list:
        return ChainReport(
            tuple(stages),
            ClaimVerdict.fail(
                ClaimCode.NO_TOOL_EVIDENCE,
                "evidenza senza cifre attese (outcome-only): niente claim numerico"),
            subject_id=f"doc-{top_idx}")

    n = int(calc_args.get("n", 1))
    first = expected_list[0]
    subject_id = f"zero-{n}" if calc_kind == "zeron" else f"{calc_kind}-{n}"
    if model_value is None:
        model_value = parse_model_claim_value(query)
    if model_value is None:
        return ChainReport(
            tuple(stages),
            ClaimVerdict.fail(
                ClaimCode.MODEL_VALUE_MISSING,
                "il claim deve nascere dal modello: model_value assente"),
            subject_id=subject_id)
    if isinstance(model_value, float):
        return ChainReport(
            tuple(stages),
            ClaimVerdict.fail(
                ClaimCode.FLOAT_FORBIDDEN,
                "il valore del claim non puo' viaggiare come float"),
            subject_id=subject_id)
    claim = NumericClaim(
        operation=calc_kind, arguments=(str(n),),
        subject_id=subject_id, value=str(model_value),
        unit=first["label"], precision=precision,
        evidence_ref=canonical_payload_hash(evidence))
    verdict = check_numeric_claim(claim, evidence)
    stages.append(WorkerResult(
        WORKER_BARRIER,
        WorkerStatus.OK if verdict.ok else WorkerStatus.ERROR,
        payload=verdict,
        message=verdict.message))
    if verdict.ok and kiarnel is not None:
        checked = _run(WORKER_KIARNEL, **dict(kiarnel))
        if checked is None:
            return ChainReport(
                tuple(stages),
                ClaimVerdict.fail(
                    ClaimCode.NO_TOOL_EVIDENCE,
                    "KIARNEL non disponibile: verifica operativa fallita"),
                subject_id=subject_id, claim=claim)
    return ChainReport(tuple(stages), verdict, subject_id=subject_id, claim=claim)


# registro i backend di default (le import sotto sforzo avvengono alla chiamata)
register_backend(WORKER_PRISM, prism_relevance)
register_backend(WORKER_CALC, calc_evidence)
register_backend(WORKER_KIARNEL, kiarnel_verify)