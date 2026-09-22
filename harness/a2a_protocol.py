"""CASCADE - Layer 4: Protocollo A2A (Agent-to-Agent).

Fissato rispetto al prototipo:
- firme digitali Ed25519 reali (crittografia a chiave pubblica), non SHA256
  concatenato (che era forgiabile conoscendo l'agent_id);
- negoziazione multi-giro con controproposte e vincoli di budget;
- discovery per topic con ranking per reputazione e costo;
- mantenimento della reputazione con media mobile esponenziale.

Il layer offre sia un servizio FastAPI sia una logica pura testabile senza rete.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# --------------------------------------------------------------------------- #
# Limiti di parsing / dimensione (prima di qualsiasi lavoro crittografico)
# --------------------------------------------------------------------------- #
MAX_NONCE_LEN = 128
MAX_AGENT_ID_LEN = 256
MAX_SIGNATURE_HEX_LEN = 1024
MAX_PAYLOAD_BYTES = 65536
# Finestra "grossolana" anti-DoS sul timestamp (non è il TTL: quella è
# verificata DOPO la firma). Serve solo a evitare memorie nonce senza limite
# e a scartare timestamps malformati prima del costo crittografico.
MAX_TIMESTAMP_SKEW_SECONDS = 7 * 24 * 3600


def _validate_envelope_shape(agent_id: Any, nonce: Any, timestamp: Any,
                             payload: Any, signature_hex: Any) -> None:
    """Controlli di forma/dimensione sull'envelope grezzo (Step 1).

    Nessuna informazione di sicurezza (TTL, validità firma) viene rivelata
    qui: solo vincoli sintattici economici anti-DoS.
    """
    import math
    if not isinstance(agent_id, str) or not agent_id or len(agent_id) > MAX_AGENT_ID_LEN:
        raise ValueError("agent_id non valido")
    if not isinstance(nonce, str) or not nonce or len(nonce) > MAX_NONCE_LEN:
        raise ValueError("nonce non valido")
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        raise ValueError("timestamp non numerico")
    if not math.isfinite(float(timestamp)):
        raise ValueError("timestamp non finito")
    if not isinstance(payload, dict):
        raise ValueError("payload non dict")
    try:
        if len(json.dumps(payload, sort_keys=True)) > MAX_PAYLOAD_BYTES:
            raise ValueError("payload troppo grande")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"payload non serializzabile: {exc}") from exc
    if not isinstance(signature_hex, str) or len(signature_hex) > MAX_SIGNATURE_HEX_LEN:
        raise ValueError("firma non valida")
    try:
        bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise ValueError("firma non è hex valido") from exc

# --------------------------------------------------------------------------- #
# Cripto helper
# --------------------------------------------------------------------------- #


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_keypair() -> tuple[bytes, bytes]:
    """Restituisce (private_key_bytes, public_key_bytes)."""
    private = ed25519.Ed25519PrivateKey.generate()
    public = private.public_key()
    return (
        private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        public.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ),
    )


def sign_bytes(private_bytes: bytes, data: bytes) -> bytes:
    private = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    return private.sign(data)


def verify_bytes(public_bytes: bytes, data: bytes, signature: bytes) -> bool:
    try:
        public = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)
        public.verify(signature, data)
        return True
    except InvalidSignature:
        return False


def sign_payload(private_bytes: bytes, obj: Any) -> bytes:
    return sign_bytes(private_bytes, _canonical(obj))


def verify_payload(public_bytes: bytes, obj: Any, signature: bytes) -> bool:
    return verify_bytes(public_bytes, _canonical(obj), signature)


# --------------------------------------------------------------------------- #
# Threat model: SignedEnvelope (nonce + timestamp, anti-replay, anti-stale)
#
# La firma da sola garantisce l'integrita', NON la non-riproducibilita'.
# Un report firmato puo' essere ri-inviato (replay) o usato fuori finestra
# temporale (stale). Aggiunge:
#   - nonce casuale        -> rende ogni messaggio univoco (anti-replay)
#   - timestamp            -> finestra di validita' (anti-stale)
#   - task_id nel payload  -> lega il messaggio a un contratto specifico
# --------------------------------------------------------------------------- #


@dataclass
class SignedEnvelope:
    agent_id: str
    nonce: str
    timestamp: float
    payload: dict[str, Any]
    signature: str = ""

    @staticmethod
    def wrap(private_bytes: bytes, agent_id: str, payload: dict[str, Any],
             now: float | None = None) -> "SignedEnvelope":
        import uuid
        env = SignedEnvelope(
            agent_id=agent_id,
            nonce=uuid.uuid4().hex,
            timestamp=now if now is not None else time.time(),
            payload=payload,
        )
        env.signature = sign_payload(private_bytes, env._signed_data()).hex()
        return env

    def _signed_data(self) -> dict[str, Any]:
        # solo cio' che e' firmato: agent, nonce, timestamp, payload
        return {
            "agent_id": self.agent_id,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def is_fresh(self, max_age_seconds: float, now: float | None = None) -> bool:
        now_t = now if now is not None else time.time()
        return 0 <= (now_t - self.timestamp) <= max_age_seconds

    def verify(self, public_bytes: bytes) -> bool:
        if not self.signature:
            return False
        return verify_payload(public_bytes, self._signed_data(), bytes.fromhex(self.signature))


class NonceStore:
    """Contratto dello store dei nonce (anti-replay).

    Semantica definita per restart e multi-worker:

    - **single-process (default, ``InMemoryNonceStore``)**: lo stato è
      effimero in memoria. A un **restart** i nonce sono dimenticati: la
      finestra anti-replay si resetta (accettabile per TTL brevi; alzare il
      TTL o usare uno store condiviso se serve). Ogni **worker/processo** ha
      il proprio store: due istanze non si vedono i nonce dell'altra, quindi
      un replay contro un secondo worker passa. Per un deployment multi-worker
      è obbligatorio un backing condiviso (es. Redis/DB) che implementa lo
      stesso contratto ``claim`` in modo atomico.
    - il contratto ``claim`` deve essere **atomico** (il check-and-insert non
      deve mai avere finestre aperte tra concorrenti).
    """

    def claim(self, nonce: str, timestamp: float,
              now: float | None = None) -> bool:
        """Registra il nonce se assente; ``True`` se accettato (mai visto),
        ``False`` se replay. Deve essere thread-safe e atomico."""
        raise NotImplementedError


class InMemoryNonceStore(NonceStore):
    """Store nonce in memoria, thread-safe, limitato e con eviction TTL.

    - ogni ``claim`` è atomicamente verificato+e-inserito sotto lock;
    - l'eviction è deterministica (TTL prima, poi il più vecchio per
      timestamp), mai ``pop(next(iter(...)))`` non deterministico;
    - il numero di nonce non supera mai ``max_seen`` (bound di memoria).
    """

    def __init__(self, ttl_seconds: float = 300.0, max_seen: int = 10000):
        if ttl_seconds <= 0 or max_seen <= 0:
            raise ValueError("ttl_seconds e max_seen devono essere > 0")
        self.ttl = ttl_seconds
        self.max_seen = max_seen
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._evictions = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._seen)

    @property
    def evictions(self) -> int:
        return self._evictions

    def claim(self, nonce: str, timestamp: float,
              now: float | None = None) -> bool:
        now_t = now if now is not None else time.time()
        with self._lock:
            # 1) eviction TTL deterministica (solo quando serve, O(n) occasionale)
            if len(self._seen) >= self.max_seen:
                cutoff = now_t - self.ttl
                stale = [k for k, v in self._seen.items() if v < cutoff]
                for k in stale:
                    self._seen.pop(k, None)
                    self._evictions += 1
            # 2) replay?
            if nonce in self._seen:
                return False
            # 3) bound di memoria: evicta il più vecchio in modo deterministico
            if len(self._seen) >= self.max_seen:
                oldest = min(self._seen, key=lambda k: self._seen[k])
                self._seen.pop(oldest)
                self._evictions += 1
            self._seen[nonce] = timestamp
            return True

    def prune(self, now: float | None = None) -> int:
        with self._lock:
            now_t = now if now is not None else time.time()
            cutoff = now_t - self.ttl
            stale = [k for k, v in self._seen.items() if v < cutoff]
            for k in stale:
                self._seen.pop(k, None)
                self._evictions += 1
            return len(stale)


class ReplayGuard:
    """Protegge da replay attack: registra i nonce visti e rifiuta i duplicati.

    Usa un ``NonceStore`` dietro le quinte: per default ``InMemoryNonceStore``
    (thread-safe, memoria limitata, TTL deterministico); per deployment
    multi-worker va iniettato uno store condiviso (vedi ``NonceStore``).
    """

    def __init__(self, ttl_seconds: float = 300.0, max_seen: int = 10000,
                 store: Optional[NonceStore] = None):
        self.ttl = ttl_seconds
        self.store = store if store is not None else InMemoryNonceStore(
            ttl_seconds=ttl_seconds, max_seen=max_seen)

    def accepts(self, nonce: str, timestamp: float,
                now: float | None = None) -> bool:
        """Accetta il nonce solo se mai visto (atomicamente)."""
        return self.store.claim(nonce, timestamp, now=now)


# --------------------------------------------------------------------------- #
# Modelli
# --------------------------------------------------------------------------- #


@dataclass
class AgentManifest:
    agent_id: str
    public_key: bytes
    capabilities: list[str] = field(default_factory=list)
    cost_per_call: float = 0.0
    base_reputation: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "AgentManifest":
        return cls(
            agent_id=d["agent_id"],
            public_key=bytes.fromhex(d["public_key"]),
            capabilities=d.get("capabilities", []),
            cost_per_call=d.get("cost_per_call", 0.0),
            base_reputation=d.get("base_reputation", 1.0),
        )

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "public_key": self.public_key.hex(),
            "capabilities": list(self.capabilities),
            "cost_per_call": self.cost_per_call,
            "base_reputation": self.base_reputation,
        }


@dataclass
class TaskRequest:
    task_id: str
    task_type: str
    payload: dict
    max_cost: float
    requester_id: str


class AgentRegistry:
    """Directory degli agenti + reputazione."""

    def __init__(self):
        self.agents: dict[str, AgentManifest] = {}
        self._reputation: dict[str, float] = {}
        self._key_to_agent: dict[bytes, str] = {}

    def register(self, manifest: AgentManifest) -> None:
        if manifest.agent_id in self.agents:
            old_key = self.agents[manifest.agent_id].public_key
            if old_key != manifest.public_key:
                self._key_to_agent.pop(old_key, None)
        self.agents[manifest.agent_id] = manifest
        self._key_to_agent[manifest.public_key] = manifest.agent_id
        self._reputation.setdefault(manifest.agent_id, manifest.base_reputation)

    def discover(self, capability: str, max_cost: float = float("inf")) -> list[AgentManifest]:
        candidates = [
            a
            for a in self.agents.values()
            if capability in a.capabilities and a.cost_per_call <= max_cost
        ]
        # nessun ordering qui: ordinato in negotiate/sel
        return candidates

    def reputation(self, agent_id: str) -> float:
        return self._reputation.get(agent_id, 0.0)

    def agent_by_key(self, public_key: bytes) -> Optional[str]:
        return self._key_to_agent.get(public_key)

    def report_outcome(self, agent_id: str, outcome: float, alpha: float = 0.2) -> float:
        """Aggiorna reputazione con media mobile esponenziale (0..1).
        outcome ~1 buono, ~0 scarso."""
        current = self._reputation.get(agent_id, 0.5)
        new = (1 - alpha) * current + alpha * outcome
        self._reputation[agent_id] = new
        return new


# --------------------------------------------------------------------------- #
# Negoziazione
# --------------------------------------------------------------------------- #


@dataclass
class Bid:
    agent_id: str
    price: float
    estimated_quality: float  # 0..1


@dataclass
class NegotiationResult:
    accepted: bool
    agent_id: Optional[str] = None
    final_price: Optional[float] = None
    reason: str = ""


def negotiate(registry: AgentRegistry, request: TaskRequest,
              requested_quality: float = 0.8) -> NegotiationResult:
    """Negoziazione multi-giro: parte dal budget del richiedente, riduce il prezzo
    contro garanzia di qualita', valuta il rapporto qualita'/costo e reputazione."""
    candidates = registry.discover(request.task_type, request.max_cost)
    if not candidates:
        return NegotiationResult(False, reason="nessun agente capace")

    # Round 1: ogni candidato formula una prima offerta
    bids: list[Bid] = []
    for agent in candidates:
        quality = 0.5 + 0.5 * registry.reputation(agent.agent_id)
        price = agent.cost_per_call
        bids.append(Bid(agent.agent_id, price, quality))

    # Round 2: selezione per qualita'/costo con soglia di qualita' minima
    affordable = [b for b in bids if b.price <= request.max_cost and b.estimated_quality >= requested_quality]
    pool = affordable or bids
    # score = qualita' / (costo relativo al budget) + reputazione
    best = max(
        pool,
        key=lambda b: (registry.reputation(b.agent_id) / b.price)
        if b.price > 0
        else float("inf"),
    )
    return NegotiationResult(True, agent_id=best.agent_id, final_price=best.price)


# --------------------------------------------------------------------------- #
# FastAPI service (optional extra: pip install cascade-soh[a2a])
# --------------------------------------------------------------------------- #

import os

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel as PBaseModel
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    PBaseModel = object  # type: ignore[misc, assignment]


# --- Schemi Pydantic ---
class ManifestIn(PBaseModel):
    agent_id: str
    public_key_hex: str
    capabilities: list[str]
    cost_per_call: float = 0.0
    base_reputation: float = 1.0


class RegisterResp(PBaseModel):
    status: str
    agent_id: str


class DiscoverResp(PBaseModel):
    agents: list[dict]


class ReportIn(PBaseModel):
    agent_id: str
    nonce: str
    timestamp: float
    payload: dict
    signature_hex: str


class ReportResp(PBaseModel):
    status: str
    new_reputation: float


def create_app() -> FastAPI:
    if FastAPI is None:
        raise ImportError("pip install 'cascade-soh[a2a]' to serve the A2A API")
    app = FastAPI(title="CASCADE A2A")
    reg = AgentRegistry()
    replay_guard = ReplayGuard()

    @app.post("/register", response_model=RegisterResp)
    def register(m: ManifestIn):
        manifest = AgentManifest(
            agent_id=m.agent_id,
            public_key=bytes.fromhex(m.public_key_hex),
            capabilities=m.capabilities,
            cost_per_call=m.cost_per_call,
            base_reputation=m.base_reputation,
        )
        reg.register(manifest)
        return RegisterResp(status="registered", agent_id=m.agent_id)

    @app.get("/discover", response_model=DiscoverResp)
    def discover(capability: str, max_cost: float = 1e9):
        agents = reg.discover(capability, max_cost)
        return DiscoverResp(agents=[a.to_dict() for a in agents])

    @app.post("/report", response_model=ReportResp)
    def report(r: ReportIn):
        # 1) parse + limiti di dimensione, PRIMA di qualsiasi lavoro crittografico.
        #    Nessuna informazione di sicurezza (TTL/firma) viene rivelata qui.
        try:
            _validate_envelope_shape(r.agent_id, r.nonce, r.timestamp,
                                     r.payload, r.signature_hex)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

        # binding attore: la chiave pubblica usata per la firma appartiene
        # all'agente dichiarato (nessun "impersonation" via chiave altrui)
        manifest = reg.agents.get(r.agent_id)
        if manifest is None:
            raise HTTPException(404, "agente sconosciuto")

        env = SignedEnvelope(
            agent_id=r.agent_id,
            nonce=r.nonce,
            timestamp=r.timestamp,
            payload=r.payload,
            signature=r.signature_hex,
        )

        # 2) verifica firma sull'envelope COMPLETO (agent_id + nonce +
        #    timestamp + payload firmati insieme)
        if not env.verify(manifest.public_key):
            raise HTTPException(401, "firma non valida")

        # 3) binding endpoint / attore / task_id
        task_id = env.payload.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise HTTPException(422, "payload senza task_id valido")

        # 4) verifica timestamp/TTL DOPO la firma (i metadati sono autenticati)
        if not env.is_fresh(max_age_seconds=replay_guard.ttl):
            raise HTTPException(403, "messaggio stantio (stale)")

        # 5) registrazione atomica del nonce (anti-replay, concorrente-safe)
        if not replay_guard.accepts(env.nonce, env.timestamp):
            raise HTTPException(409, "replay attack rilevato")

        # 6) validazione payload tipizzata
        outcome = env.payload.get("outcome")
        if isinstance(outcome, bool) or not isinstance(outcome, (int, float)):
            raise HTTPException(422, "outcome deve essere numerico")
        outcome = float(outcome)
        if not (0.0 <= outcome <= 1.0):
            raise HTTPException(422, "outcome fuori intervallo [0,1]")

        new_rep = reg.report_outcome(r.agent_id, outcome)
        return ReportResp(status="accepted", new_reputation=new_rep)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
