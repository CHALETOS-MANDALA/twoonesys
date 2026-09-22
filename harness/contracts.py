"""CASCADE - Contratti comuni tra i layer.

Definisce il vocabolario condiviso che ogni layer usa per parlare con gli
altri. Senza questo, ogni layer resta una demo isolata: qui standardizziamo
Input (richiesta), Output (decisione certificata) e Context (metadati che
fluiscono tra causale, memoria, guard e world model).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def canonical_json(obj: Any) -> bytes:
    """Serializzazione canonica stabile (per hash e firme)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


@dataclass
class DecisionCertificate:
    """Certificato verificabile e riproducibile di una decisione.

    Risponde alla critica 'formalmente verificato e' troppo largo': ogni
    decisione porta con se' le versioni esatte di policy, modelli e solver,
    l'hash degli input e una firma. Senza questo, un incidente e' archeologia.
    """

    decision_id: str
    input_hash: str
    policy_version: str
    model_versions: dict[str, str] = field(default_factory=dict)
    solver_status: str = ""
    proof_constraints: list[str] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty_bounds: dict[str, float] = field(default_factory=dict)
    approved: bool = False
    created_at: float = 0.0
    expires_at: float = 0.0
    signature: str = ""
    # quale chiave ha firmato: senza, dopo una rotazione il certificato non e'
    # piu' verificabile perche' nessuno sa quale pubblica usare.
    key_id: str = ""

    @classmethod
    def create(cls, decision_id: str, input_obj: Any, policy_version: str,
               model_versions: dict[str, str], solver_status: str,
               proof_constraints: list[str], confidence: float,
               approved: bool, ttl_seconds: float = 5.0,
               uncertainty_bounds: Optional[dict[str, float]] = None,
               now: Optional[float] = None) -> "DecisionCertificate":
        now_t = now if now is not None else time.time()
        return cls(
            decision_id=decision_id,
            input_hash=sha256_hex(input_obj),
            policy_version=policy_version,
            model_versions=model_versions,
            solver_status=solver_status,
            proof_constraints=proof_constraints,
            confidence=confidence,
            uncertainty_bounds=uncertainty_bounds or {},
            approved=approved,
            created_at=now_t,
            expires_at=now_t + ttl_seconds,
        )

    # -- riproducibilita' / verifica ----------------------------------------- #
    def payload(self) -> bytes:
        """Contenuto da firmare/verificare (senza la firma stessa)."""
        d = asdict(self)
        d.pop("signature", None)
        return canonical_json(d)

    def is_expired(self, now: Optional[float] = None) -> bool:
        now_t = now if now is not None else time.time()
        return self.expires_at > 0 and now_t > self.expires_at

    def verify_signature(self, public_key_bytes: bytes) -> bool:
        """Verifica la firma Ed25519 del certificato."""
        from .a2a_protocol import verify_bytes
        if not self.signature:
            return False
        return verify_bytes(public_key_bytes, self.payload(), bytes.fromhex(self.signature))

    def sign(self, private_key_bytes: bytes) -> "DecisionCertificate":
        from .a2a_protocol import sign_bytes
        self.signature = sign_bytes(private_key_bytes, self.payload()).hex()
        return self

    def sign_with(self, identity) -> "DecisionCertificate":
        """Firma registrando ANCHE quale chiave ha firmato (`SigningIdentity`)."""
        self.key_id = identity.key_id
        self.signature = identity.sign(self.payload()).hex()
        return self

    def verify_in(self, registry) -> bool:
        """Verifica tramite lo storico delle chiavi: regge una rotazione.

        Una chiave sconosciuta NON e' un dubbio da risolvere in positivo:
        e' un certificato non verificabile.
        """
        if not self.signature or not self.key_id:
            return False
        return registry.verify(self.key_id, self.payload(), bytes.fromhex(self.signature))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentSignal:
    """Decisione/azione proposta da un agente o dal modulo neurale."""
    agent_id: str
    proposal: dict[str, Any]          # azione / output neurale
    confidence: float                  # 0..1
    capability: str


@dataclass
class Task:
    """Richiesta end-to-end che attraversa tutti i layer."""
    task_id: str
    capability: str
    request: dict[str, Any]            # payload della richiesta
    max_cost: float = 10.0


@dataclass
class CausalEvidence:
    """Risultati del layer causale (Layer 1)."""
    posteriors: dict[str, dict[Any, float]] = field(default_factory=dict)
    interventions: list[dict] = field(default_factory=list)
    counterfactuals: list[dict] = field(default_factory=list)


@dataclass
class WorldForecast:
    """Previsione del world model (Layer 3). Una singola previsione puntuale
    nasconde l'incertezza: per il controllo serve la distribuzione + la
    decomposizione epistemica/aleatorica (review punto 4)."""
    predicted_next_state: Any = None
    stable: bool = True
    note: str = ""
    latent_mean: Any = None
    latent_covariance: Any = None
    horizon: int = 1
    epistemic_uncertainty: Optional[float] = None
    aleatoric_uncertainty: Optional[float] = None
    ood_score: Optional[float] = None  # alto = fuori distribuzione


@dataclass
class Decision:
    """Output certificato del pipeline (contratto finale)."""
    task_id: str
    approved: bool = False
    final_output: Optional[dict[str, Any]] = None
    certified: bool = False
    agent_id: Optional[str] = None
    violations: list[dict] = field(default_factory=list)
    evidence: Optional[CausalEvidence] = None
    forecast: Optional[WorldForecast] = None
    certificate: Optional[DecisionCertificate] = None
    abstained: bool = False       # astensione esplicita (OOD / bassa confidenza)
    abstain_reason: str = ""
