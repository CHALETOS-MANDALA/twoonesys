"""CASCADE - Ponte ENI <-> Pipeline.

ENI (brain_ai/app.py, una standalone "Enterprise Brain" con pipeline cognitiva)
diventa il PERCORSO NEURALE REALE di CASCADE. Risolve la critica che i numeri di
confidenza nel pipeline erano fittizi/hardcodati: ora la confidenza e l'azione
arrivano dalla decisione vera di ENI su Ollama, e la causale + guard Z3 le
verificano prima di autorizzare.

Flusso:
    proposta problema
      -> ENI /decision   (confidenza reale, ramo migliore, rationale)
      -> ENI /forecast   (acceptance_probability, stato)
      -> AgentSignal     (azione + confidenza reali)
      -> CascadePipeline (causale -> guard Z3 -> decisione certificata)

Il client e' iniettabile (callback `call_fn`) cosi' i test possono simulare ENI
senza rete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional

import httpx

from .contracts import AgentSignal

try:
    from .a2a_protocol import AgentManifest, generate_keypair
except ImportError:
    from a2a_protocol import AgentManifest, generate_keypair


class ProposalUnavailable(RuntimeError):
    """ENI non ha fornito un'azione TIPIZZATA e nessun default e' stato dato."""


def _typed_action(payload: Mapping[str, Any]) -> Optional[float]:
    """Azione presa SOLO da un campo strutturato, mai dalla prosa.

    Prima l'azione di controllo veniva estratta con una regex dal `rationale`
    del modello (il primo numero del testo): con *"in 2 casi su 3 consiglio
    azione 2.5"* si ottiene 2, e quel numero finisce a un attuatore. E' il
    pattern che la barriera dei claim esiste per impedire, applicato al
    percorso decisionale.

    Ora: il campo c'e' ed e' un numero finito, oppure non c'e' azione.
    """
    for source in (payload, payload.get("best_branch") or {}):
        if not isinstance(source, Mapping):
            continue
        raw = source.get("action")
        if raw is None or isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


class ENIBrain:
    """Client verso il cervello standalone ENI (brain_ai/app.py)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        agent_id: str = "eni-1",
        timeout: float = 60.0,
        call_fn: Optional[Callable[[str, dict, float], Awaitable[dict]]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.agent_id = agent_id
        # callback iniettabile per i test (simula ENI senza rete)
        self._call = call_fn or self._default_call
        self._priv: Optional[bytes] = None
        self._pub: Optional[bytes] = None

    async def _default_call(self, endpoint: str, payload: dict,
                            timeout: float) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.base_url}{endpoint}", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def decision(self, problem: str) -> dict[str, Any]:
        """Chiama /decision e ritorna (confidenza, ramo migliore, rationale)."""
        data = await self._call("/decision", {"problem": problem}, self.timeout)
        d = data.get("decision", {})
        return {
            "confidence": float(d.get("confidence", 0.0) or 0.0),
            "best_scenario": (d.get("best_branch", {}) or {}).get("scenario", ""),
            "rationale": d.get("rationale", ""),
            "action": _typed_action(d),      # campo strutturato, non la prosa
            "best_probability": float((d.get("best_branch", {}) or {}).get("posterior", 0.0) or 0.0),
        }

    async def forecast(self, problem: str) -> dict[str, Any]:
        """Chiama /forecast e ritorna acceptance_probability + stato."""
        data = await self._call("/forecast", {"problem": problem}, self.timeout)
        state = data.get("state_vector", {}) or {}
        return {
            "acceptance_probability": int(data.get("acceptance_probability", 0) or 0),
            "state_confidence": float(state.get("confidence", 0.0) or 0.0),
            "risk": float(state.get("risk", 0.0) or 0.0),
            "uncertainty_text": data.get("uncertainty", ""),
        }

    async def propose(self, problem: str,
                      default_action: Optional[float] = None) -> AgentSignal:
        """Proposta di azione da ENI, con provenienza dichiarata.

        L'azione arriva SOLO da un campo tipizzato della risposta. Se ENI non
        lo fornisce non viene inventata: o il chiamante ha passato un
        `default_action` esplicito (e la proposta lo dichiara), oppure si alza
        `ProposalUnavailable`.

        La confidenza resta un PUNTEGGIO GREZZO non calibrato: e' una media
        pesata di due numeri che il modello dichiara su se stesso. Finche' non
        passa da un calibratore misurato non e' una probabilita', e il campo
        `confidence_kind` lo dice a chi la riceve.
        """
        dec = await self.decision(problem)
        fc = await self.forecast(problem)

        action = dec.get("action")
        source = "eni_typed"
        if action is None:
            if default_action is None:
                raise ProposalUnavailable(
                    "ENI non ha fornito un campo `action` tipizzato e nessun "
                    "default e' stato indicato: nessuna azione viene dedotta "
                    "dal testo della rationale.")
            action = float(default_action)
            source = "caller_default"

        conf_dec = dec["confidence"]
        conf_fc = fc["acceptance_probability"] / 100.0
        raw_score = 0.6 * conf_dec + 0.4 * conf_fc

        return AgentSignal(
            agent_id=self.agent_id,
            proposal={"action": float(action),
                      "scenario": dec.get("best_scenario", ""),
                      "action_source": source,
                      "confidence_kind": "raw_uncalibrated"},
            confidence=float(max(0.0, min(1.0, raw_score))),
            capability="controllo",
        )

    def manifest(self, cost: float = 0.1, reputation: float = 0.8) -> AgentManifest:
        """Manifest A2A di ENI. La chiave privata viene CONSERVATA: prima
        veniva scartata (`_, pub = generate_keypair()`), quindi l'agente
        risultava registrato con una pubblica di cui nessuno aveva la privata
        e non avrebbe mai potuto firmare un report."""
        if self._priv is None:
            self._priv, self._pub = generate_keypair()
        priv, pub = self._priv, self._pub
        return AgentManifest(
            agent_id=self.agent_id,
            public_key=pub,
            capabilities=["controllo", "reasoning"],
            cost_per_call=cost,
            base_reputation=reputation,
        )


# --------------------------------------------------------------------------- #
# Fake ENI per test (nessuna rete)
# --------------------------------------------------------------------------- #


async def fake_eni_response(endpoint: str, payload: dict, timeout: float) -> dict:
    """Simula ENI in modo deterministico per i test del bridge."""
    if endpoint == "/decision":
        return {
            "decision": {
                "confidence": 0.9,
                "action": 2.5,          # campo TIPIZZATO: e' questo che conta
                "best_branch": {"scenario": "azione ridotta progressiva",
                                "posterior": 0.85},
                "rationale": "Scelta: azione di controllo 2.5 con verifica incrementale",
            }
        }
    if endpoint == "/forecast":
        return {
            "acceptance_probability": 80,
            "state_vector": {"confidence": 0.85, "risk": 0.2},
            "uncertainty": "incertezza bassa",
        }
    raise ValueError(f"endpoint sconosciuto: {endpoint}")
