"""TWOONESYS - Rizzo Flow (engine) come proponente di CASCADE (harness).

Specchio di latent_bridge.py: l'engine (System One modello, :8017) emette la
decisione tipizzata con probabilita' reale letta dai logit - zero token
generati; l'harness (System One harness) decide se lasciarla agire.
Il ponte TRADUCE, non giudica:

    choice            -> action_chosen (identita' del braccio, non il nome del modello)
    p(valore scelto)  -> raw_confidence (segnale vero: mai 0.5 cablato)
    numeric           -> model_value per la claim barrier (cifre dal modello,
                         mai una regex sulla prosa)
    status != "ok"    -> astensione dell'engine: l'harness non autorizza MAI,
                         il caso va al System 2.

Regole di onesta' ereditate da CASCADE:
* engine irraggiungibile o risposta malformata -> RizzoBridgeError,
  mai un proseguimento di comodo;
* la confidenza riportata e' quella dell'engine, NON ricalibrata:
  la calibrazione sugli esiti osservati resta del ReliabilityMeter;
* nessun numero inventato: se l'engine si astiene, value=None e il record
  conserva lo status che spiega perche'.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8017"
DECISIONS_PATH = "/v1/decisions"

STATUSES = frozenset({"ok", "insufficient_evidence", "out_of_range", "uncertain"})


class RizzoBridgeError(RuntimeError):
    """L'engine TWOONESYS (:8017) non ha prodotto una decisione valida."""


@dataclass(frozen=True)
class RizzoProposal:
    """Proposta tipizzata dell'engine, prima di qualunque verifica."""

    question: str
    answer_type: str                       # boolean | choice | score | numeric
    status: str                            # ok | insufficient_evidence | out_of_range | uncertain
    value: str | None                      # rendering del valore scelto (None = astensione)
    confidence: float                      # p del valore scelto, dai logit - non ricalibrata
    top_probability: float
    unavailable_probability: float
    probabilities: dict[str, float]
    model_value: str | None                # solo numeric: decimale per la claim barrier
    model_id: str
    prompt_sha256: str
    latency_ms: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def abstained(self) -> bool:
        """L'engine non ha evidenza sufficiente: l'harness non autorizza."""
        return self.status != "ok" or self.value is None

    def to_agent_signal(self, *, agent_id: str = "twoonesys-engine"):
        from cascade.contracts import AgentSignal

        return AgentSignal(
            agent_id=agent_id,
            proposal={
                "text": self.value,
                "question": self.question,
                "answer_type": self.answer_type,
                "status": self.status,
                "probabilities": self.probabilities,
                "unavailable_probability": self.unavailable_probability,
                "prompt_sha256": self.prompt_sha256,
            },
            confidence=self.confidence,
            capability="system_one_decision",
        )


def _model_id(model: Any) -> str:
    if isinstance(model, Mapping):
        for key in ("id", "model", "name"):
            if model.get(key):
                return str(model[key])
        return "twoonesys-engine"
    return str(model) if model else "twoonesys-engine"


def _extract(answer_type: str, answer: Mapping[str, Any]) -> tuple[str | None, float, str | None]:
    """(value, confidence, model_value) dalla risposta dell'engine.

    confidence = probabilita' del valore SCELTO (non la top in assoluto):
    e' il numero che l'harness ricalibrera' sugli esiti.
    """
    unc = answer.get("uncertainty") or {}
    top_p = float(unc.get("top_probability", 0.0))
    probs = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}

    if answer_type == "boolean":
        val = answer.get("value")
        p_true = answer.get("probability_true_given_available")
        if val is None or p_true is None:
            return None, top_p, None
        p = float(p_true) if val else 1.0 - float(p_true)
        return ("true" if val else "false"), p, None

    if answer_type == "choice":
        choice = answer.get("choice")
        if choice is None:
            return None, top_p, None
        return str(choice), probs.get(str(choice), top_p), None

    if answer_type == "score":
        score = answer.get("score")
        if score is None:
            return None, top_p, None
        return str(score), top_p, None

    if answer_type == "numeric":
        value = answer.get("value")
        if value is None:
            return None, top_p, None
        # claim barrier: il claim e' l'ancora che il modello ha SCELTO
        # (argmax sulle probabilita'), non la media pesata — la media e'
        # una stima, la barriera vuole la cifra dichiarata.
        values_map = answer.get("values") or {}
        chosen_id = max(probs, key=probs.get) if probs else None
        model_value = None
        if chosen_id is not None and chosen_id in values_map:
            model_value = str(values_map[chosen_id])
        return str(value), top_p, model_value

    raise RizzoBridgeError(f"tipo di risposta sconosciuto: {answer_type!r}")


class RizzoProposer:
    """Client HTTP verso l'engine TWOONESYS.

    `post_fn` iniettabile per i test: la suite non tocca la rete
    (stesso patto di fake_eni_response per ENI).
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 60.0,
                 api_key: str | None = None,
                 post_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self._post_fn = post_fn

    def health(self) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise RizzoBridgeError(
                f"engine non raggiungibile su {self.base_url}: {exc}") from exc
        return response.json()

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._post_fn is not None:
            try:
                data = self._post_fn(payload)
            except RizzoBridgeError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise RizzoBridgeError(
                    f"engine (post_fn iniettato) fallito: {exc}") from exc
        else:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            try:
                response = httpx.post(f"{self.base_url}{DECISIONS_PATH}", json=payload,
                                      headers=headers, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                raise RizzoBridgeError(
                    f"engine non raggiungibile o risposta non valida: {exc}") from exc
        if not isinstance(data, dict) or "answers" not in data:
            raise RizzoBridgeError("risposta senza campo 'answers'")
        return data

    def propose(self, state: Any, questions: Mapping[str, Any], *,
                question: str | None = None, mode: str = "shared") -> RizzoProposal:
        """Una richiesta /v1/decisions -> UNA proposta (la domanda scelta).

        Piu' domande nella stessa richiesta condividono la KV cache dello
        stato (e' il punto dell'engine): `question` sceglie quale risposta
        diventa la proposta; le altre restano in raw per l'harness.
        """
        if not questions:
            raise ValueError("almeno una domanda e' necessaria")
        payload = {"state": state, "questions": dict(questions), "mode": mode}
        started = time.perf_counter()
        data = self._post(payload)
        latency_ms = (time.perf_counter() - started) * 1000.0

        answers = data.get("answers") or {}
        name = question or next(iter(questions))
        if name not in answers:
            raise RizzoBridgeError(f"risposta mancante per la domanda {name!r}")
        answer = answers[name]
        answer_type = str(answer.get("type", ""))
        value, confidence, model_value = _extract(answer_type, answer)

        status = str(answer.get("status", "uncertain"))
        if status not in STATUSES:
            raise RizzoBridgeError(f"status sconosciuto: {status!r}")
        unc = answer.get("uncertainty") or {}

        return RizzoProposal(
            question=name,
            answer_type=answer_type,
            status=status,
            value=value,
            confidence=max(0.0, min(1.0, float(confidence))),
            top_probability=float(unc.get("top_probability", 0.0)),
            unavailable_probability=float(unc.get("unavailable_probability", 0.0)),
            probabilities={str(k): float(v)
                           for k, v in (answer.get("probabilities") or {}).items()},
            model_value=model_value,
            model_id=_model_id(data.get("model")),
            prompt_sha256=str(answer.get("prompt_sha256", "")),
            latency_ms=latency_ms,
            raw=dict(answer),
        )
