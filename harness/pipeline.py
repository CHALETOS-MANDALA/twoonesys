"""CASCADE - Orchestratore end-to-end (integrazione dei 5 layer).

Scenario di riferimento: un agente di controllo stabilizza un sistema fisico
(ToyOscillator) proponendo un'azione di controllo. Il pipeline fa passare la
proposta attraverso TUTTI i layer prima di autorizzarla:

  1. A2A (Layer 4)      -> negozia un agente capace per il task
  2. World Model (L3)   -> prevede lo stato futuro (foresight)
  3. Causal Engine (L1) -> inferenza sul rischio + controfattuale di sicurezza
  4. Guard (L5)         -> verifica formale Z3 di sicurezza e confidenza
  5. Memory (L2)        -> registra l'esito e addestra in modo continuo

L'orchestratore espone `run(task, proposals)` che attraversa tutti i layer e
ritorna un `Decision` certificato. E' il collante che trasforma 5 demo in un
unico sistema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import torch
import torch.nn as nn

try:
    from .a2a_protocol import AgentManifest, AgentRegistry, TaskRequest, negotiate
    from .causal_engine import CPD, CausalModel, CausalNode
    from .continuous_memory import ContinualLearner, ProgressiveNet
    from .contracts import (
        AgentSignal,
        CausalEvidence,
        Decision,
        DecisionCertificate,
        Task,
        WorldForecast,
    )
    from .neurosymbolic_guard import (
        ConfidenceLevel,
        NeurosymbolicGuard,
        SymbolicContract,
    )
except ImportError:  # esecuzione diretta come script
    from a2a_protocol import AgentManifest, AgentRegistry, TaskRequest, negotiate
    from causal_engine import CPD, CausalModel, CausalNode
    from continuous_memory import ContinualLearner, ProgressiveNet
    from contracts import (
        AgentSignal, CausalEvidence, Decision, DecisionCertificate, Task, WorldForecast,
    )
    from neurosymbolic_guard import ConfidenceLevel, NeurosymbolicGuard, SymbolicContract



# --------------------------------------------------------------------------- #
# Guard di sicurezza specifica per il controllo
# --------------------------------------------------------------------------- #


def build_control_guard(max_abs_action: float = 5.0,
                        threshold: ConfidenceLevel | float = ConfidenceLevel.GENERAL,
                        vel_max: float = 3.0) -> NeurosymbolicGuard:
    """Guard con vincoli formali Z3 sul controllo.

    Vincoli verificati dal theorem prover:
    - azione entro [-max_abs_action, +max_abs_action]
    - velocita' futura prevista entro limite di sicurezza

    `threshold` e `vel_max` sono parametrizzati: arrivano dal PipelineConfig,
    cosi' la soglia di confidenza e la soglia di velocita' sono un'unica fonte
    di verita' (niente hardcode che ignora la configurazione).
    """
    import z3

    guard = NeurosymbolicGuard(threshold)

    action = z3.Real("action")
    guard.add_contract(SymbolicContract(
        name="azione_entro_budget",
        expressions=[z3.And(action <= max_abs_action, action >= -max_abs_action)],
        symbols={"action": action},
    ))

    vel = z3.Real("vel_fut")
    guard.add_contract(SymbolicContract(
        name="velocita_sicura",
        expressions=[z3.And(vel <= vel_max, vel >= -vel_max)],
        symbols={"vel_fut": vel},
    ))
    return guard


# --------------------------------------------------------------------------- #
# Modello causale del rischio (Layer 1)
# --------------------------------------------------------------------------- #


def build_risk_model() -> CausalModel:
    """Grafo causale: ipercontrollo -> destabilizzazione -> incidente."""
    m = CausalModel()
    m.add_variable(CausalNode("ipercontrollo", values=[True, False]))
    m.add_variable(CausalNode("rumore", values=[True, False]))
    m.add_variable(CausalNode(
        "destabilizza",
        cpd=CPD(
            "destabilizza",
            ["ipercontrollo", "rumore"],
            {
                (True, True): {True: 0.9, False: 0.1},
                (True, False): {True: 0.4, False: 0.6},
                (False, True): {True: 0.3, False: 0.7},
                (False, False): {True: 0.05, False: 0.95},
            },
        ),
    ), parents=["ipercontrollo", "rumore"])
    m.add_variable(CausalNode(
        "incidente",
        cpd=CPD(
            "incidente",
            ["destabilizza"],
            {(True,): {True: 0.95, False: 0.05}, (False,): {True: 0.1, False: 0.9}},
        ),
    ), parents=["destabilizza"])
    return m


# --------------------------------------------------------------------------- #
# World Model compatto (Layer 3)
# --------------------------------------------------------------------------- #


class CompactWorldModel(nn.Module):
    """World model leggero che predice la variazione di stato (delta) da
    (stato, azione) concatenati. L'input e' `cat(obs, action)` per rispettare il
    contratto `(x, y)` del ContinualLearner (Layer 2)."""

    def __init__(self, obs_dim: int = 2, action_dim: int = 1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim + action_dim, 32),
            nn.ReLU(),
            nn.Linear(32, obs_dim),
        )

    def forward(self, x):
        return self.net(x)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #


@dataclass
class PipelineConfig:
    max_action: float = 5.0
    confidence_threshold: float | ConfidenceLevel = ConfidenceLevel.GENERAL
    memory_lr: float = 1e-2
    memory_epochs: int = 4
    ewc_lambda: float = 500.0
    risk_threshold: float = 0.5   # P(incidente) oltre cui si mitiga/blocca
    safety_vel_max: float = 3.0   # unica soglia di sicurezza (symbolic)
    max_mitigations: int = 3      # quante volte ridurre l'azione prima di bloccare
    mitigation_factor: float = 0.5
    max_ood: float = 1.0          # soglia OOD oltre cui ASTENERSI (review p.3)
    cert_ttl_seconds: float = 5.0  # TTL del certificato decisionale (review p.2)

    def threshold_value(self) -> float:
        """Ritorna la soglia come float, sia che sia un ConfidenceLevel sia un
        numero puro (utile per il CLI e per costruire il guard)."""
        t = self.confidence_threshold
        return t.value if isinstance(t, ConfidenceLevel) else float(t)


class CascadePipeline:
    """Integra i 5 layer in un unico flusso decisionale certificato."""

    def __init__(self, config: Optional[PipelineConfig] = None,
                 identity=None, key_store=None, key_registry=None):
        self.config = config or PipelineConfig()

        # Layer 1
        self.risk_model = build_risk_model()

        # Layer 2
        self.world_nn = CompactWorldModel()
        self.memory = ContinualLearner(
            self.world_nn,
            lr=self.config.memory_lr,
            lambda_ewc=self.config.ewc_lambda,
            epochs_per_task=self.config.memory_epochs,
            regression=True,
        )

        # Layer 3
        self.toy = ToyOscillator2()   # set below

        # Layer 4
        self.registry = AgentRegistry()

        # Layer 5
        self.guard = build_control_guard(
            self.config.max_action,
            threshold=self.config.threshold_value(),
            vel_max=self.config.safety_vel_max,
        )

        # Identita' di firma PERSISTENTE + storico delle chiavi: un certificato
        # deve restare verificabile dopo un riavvio del processo (prima la
        # coppia veniva rigenerata a ogni __init__, quindi no).
        from .signing import KeyRegistry, SigningIdentity
        self.identity = identity or SigningIdentity.load_or_create(key_store)
        self.key_registry = key_registry if key_registry is not None else KeyRegistry(
            None if key_store is None else Path(key_store).with_name("known_keys.json"))
        self.key_registry.register(self.identity)
        self.policy_version = "policy-v1"

    @property
    def _sign_priv(self) -> bytes:
        return self.identity.private_bytes

    @property
    def _sign_pub(self) -> bytes:
        return self.identity.public_bytes

    def register_agent(self, manifest: AgentManifest) -> None:
        self.registry.register(manifest)

    # -- certificate (review p.2) -------------------------------------------- #
    def _make_certificate(self, task: Task, decision: Decision,
                          confidence: float, action: float,
                          solver_status: str, state=None,
                          noise: bool = False) -> DecisionCertificate:
        """`solver_status` e `state` sono PARAMETRI OBBLIGATORI del chiamante.

        Prima erano dedotti: `"sat" if decision.approved else "blocked"` non
        veniva dal solver ma dal flag di approvazione (un claim senza evidenza
        dentro l'artefatto che esiste per essere evidenza), e `state_in`
        leggeva `decision._state`, mai assegnato: lo stato non entrava
        nell'hash e due decisioni da stati diversi avevano lo stesso
        `input_hash`.
        """
        proof = []
        if decision.evidence:
            proof.append(f"P(incidente)={decision.evidence.posteriors.get('P(incidente)', {}).get(True, 0.0):.3f}")
        if decision.forecast is not None:
            proof.append(f"vel_fut={decision.forecast.predicted_next_state[1] if decision.forecast.predicted_next_state else 0.0:.3f}")
        cert = DecisionCertificate.create(
            decision_id=task.task_id,
            input_obj={"request": task.request, "action": action,
                       "state_in": list(state) if state is not None else None,
                       "noise": bool(noise)},
            policy_version=self.policy_version,
            model_versions={"world_model": "compact-v1", "causal": "risk-v1",
                            "guard_z3": "contracts-v1"},
            solver_status=solver_status,
            proof_constraints=proof,
            confidence=confidence,
            approved=decision.approved,
            ttl_seconds=self.config.cert_ttl_seconds,
            uncertainty_bounds=(
                {"epistemic": decision.forecast.epistemic_uncertainty,
                 "aleatoric": decision.forecast.aleatoric_uncertainty,
                 "ood": decision.forecast.ood_score}
                if decision.forecast is not None else {}
            ),
        )
        return cert.sign_with(self.identity)

    # -- foresight (Layer 3) ------------------------------------------------- #
    def foresee(self, state, action, ood_probe: Optional[float] = None) -> WorldForecast:
        """Predice lo stato futuro dato il controllo proposto e ne valuta la
        stabilita'. `ood_probe` (opzionale) permette al chiamante di iniettare uno
        score fuori-distribuzione (altrimenti calcolato come deviazione dello
        stato dall'inerzia del sistema)."""
        obs = torch.tensor([state], dtype=torch.float32)
        act = torch.tensor([[action]], dtype=torch.float32)
        self.world_nn.eval()
        with torch.no_grad():
            d = self.world_nn(torch.cat([obs, act], dim=-1))
        next_state = (obs + d).squeeze(0).tolist()
        vel = next_state[1]
        stable = abs(vel) <= self.config.safety_vel_max

        # Incertezza (review p.4): sezione di prova. Una stima onesta del
        # world model reale richiede MC-dropout/ensemble; qui usiamo una proxy:
        # la magnitudine della variazione prevista come incertezza di
        # previsione + un'componente aleatorica fissa.
        if ood_probe is None:
            ood_probe = float(abs(obs[0, 0].item()))  # |pos| come proxy OOD
        aleatoric = 0.02
        epistemic = ood_probe * 0.1 + 0.01
        return WorldForecast(
            predicted_next_state=next_state,
            stable=stable,
            note="ok" if stable else f"velocita' prevista {vel:.2f} oltre soglia",
            latent_mean=next_state,
            latent_covariance=None,
            horizon=1,
            epistemic_uncertainty=epistemic,
            aleatoric_uncertainty=aleatoric,
            ood_score=ood_probe,
        )

    # -- causal reasoning (Layer 1) ------------------------------------------ #
    def reason_risk(self, action: float, noise: bool) -> CausalEvidence:
        """Calcola il rischio causale: P(incidente) e controfattuale."""
        iper = abs(action) > self.config.max_action * 0.7
        ev = CausalEvidence()
        ev.posteriors["P(incidente)"] = self.risk_model.posterior(
            "incidente", {"ipercontrollo": iper, "rumore": noise}
        )
        # controfattuale: se NON fossimo in ipercontrollo, quanto rischieremmo?
        cf = self.risk_model.counterfactual(
            "incidente", {"ipercontrollo": False}, {"ipercontrollo": iper, "rumore": noise}
        )
        ev.counterfactuals.append({"se_non_ipercontrollo": cf})
        return ev

    # -- memory update (Layer 2) --------------------------------------------- #
    def remember(self, task_id: int, states: Iterable, actions: Iterable) -> None:
        """Addestra in modo continuo il world model sui dati osservati.
        Input = cat(stato, azione), target = variazione di stato (delta)."""
        obs = torch.tensor(list(states), dtype=torch.float32)
        act = torch.tensor(list(actions), dtype=torch.float32).unsqueeze(-1)
        targets = torch.empty_like(obs)
        targets[:-1] = obs[1:]
        targets[-1] = obs[-1]
        deltas = targets - obs
        xs = torch.cat([obs, act], dim=-1)
        data = list(zip(xs, deltas))
        loader = torch.utils.data.DataLoader(data, batch_size=8, shuffle=True)
        self.memory.train_task(task_id, loader, nn.MSELoss(), task_lr=self.config.memory_lr)

    # -- main flow ------------------------------------------------------------ #
    def run(self, task: Task, proposals: list[AgentSignal],
            state, noise: bool = False) -> Decision:
        """Esegue il flusso end-to-end su una proposta di controllo.

        Fix 3: l'agente vincitore e' scelto dalla VERA negoziazione A2A
               (reputazione/costo/qualita'), non da max(confidence).
        Fix 1: l'evidenza causale DIVENTA un gate: se P(incidente) supera la
               soglia, l'azione viene mitigata (o bloccata dopo N tentativi).
        Fix 2: una SOLA policy di sicurezza, valutata simbolicamente dal guard
               Z3 (azione + velocita' futura). Niente doppio gate manuale.
        """
        dec = Decision(task_id=task.task_id)

        # -- Layer 4: negoziazione A2A reale -------------------------------- #
        winner = self._negotiate(task, proposals)
        if winner is None:
            dec.approved = False
            dec.violations.append({"layer": "a2a", "type": "no_agent"})
            return dec
        dec.agent_id = winner.agent_id
        confidence = float(winner.confidence)
        # azione iniziale = quella proposta dall'agente vincitore
        action = float(winner.proposal.get("action", 0.0))

        mitigations = 0
        while True:
            # -- Layer 3: foresight ---------------------------------------- #
            forecast = self.foresee(state, action)
            dec.forecast = forecast

            # -- OOD abstention (review p.3) -------------------------------- #
            if (forecast.ood_score is not None
                    and forecast.ood_score > self.config.max_ood):
                dec.abstained = True
                dec.abstain_reason = (
                    f"out_of_distribution (ood={forecast.ood_score:.2f} > "
                    f"{self.config.max_ood})"
                )
                dec.approved = False
                dec.final_output = None
                dec.violations.append({
                    "layer": "world", "type": "out_of_distribution",
                    "ood_score": forecast.ood_score,
                    "soglia": self.config.max_ood,
                })
                dec.certificate = self._make_certificate(task, dec, confidence, action,
                    solver_status="not_invoked", state=state, noise=noise)
                return dec

            # -- Layer 1: ragionamento causale (ora DECIDE) ------------------ #
            evidence = self.reason_risk(action, noise)
            dec.evidence = evidence
            p_incident = evidence.posteriors.get("P(incidente)", {}).get(True, 0.0)

            # -- Layer 5: policy di sicurezza UNICA (Z3) ---------------------- #
            ctx = {
                "action": action,
                "confidence": confidence,
                "vel_fut": (forecast.predicted_next_state[1]
                            if forecast.predicted_next_state else 0.0),
                "safe_fallback": {"action": 0.0, "note": "azione azzerata (fallback)"},
            }
            final_out, guard_ok = self.guard.validate(winner.proposal, ctx)

            if not guard_ok:
                # policy di sicurezza violata -> mitiga o blocca
                if mitigations < self.config.max_mitigations:
                    action *= self.config.mitigation_factor
                    mitigations += 1
                    continue
                dec.approved = False
                dec.final_output = final_out
                dec.violations.append({
                    "layer": "guard", "type": "safety_policy_violation",
                    "detail": guard_violation_detail(self.guard),
                })
                dec.certificate = self._make_certificate(task, dec, confidence, action,
                    solver_status="violation", state=state, noise=noise)
                return dec

            # -- Fix 1: gate causale -------------------------------- #
            if p_incident > self.config.risk_threshold:
                if mitigations < self.config.max_mitigations:
                    action *= self.config.mitigation_factor
                    mitigations += 1
                    continue
                dec.approved = False
                dec.final_output = {"action": action, "note": "bloccato per rischio causale"}
                dec.violations.append({
                    "layer": "causal", "type": "risk_threshold_exceeded",
                    "P(incidente)": p_incident,
                    "soglia": self.config.risk_threshold,
                })
                dec.certificate = self._make_certificate(task, dec, confidence, action,
                    solver_status="rules_verified", state=state, noise=noise)
                return dec

            # mitigato? annotiamo la riduzione applicata
            if mitigations > 0:
                dec.final_output = {
                    "action": action,
                    "note": f"autorizzato dopo {mitigations} riduzioni (mitigazione causale/sicurezza)",
                }
            else:
                dec.final_output = {"action": action, "note": "autorizzato e certificato"}
            dec.approved = True
            dec.certified = True
            dec.certificate = self._make_certificate(task, dec, confidence, action,
                solver_status="rules_verified", state=state, noise=noise)
            return dec

    def _negotiate(self, task: Task, proposals: list[AgentSignal]):
        """Usa la VERA negoziazione A2A (reputazione/costo/qualita') per
        scegliere l'agente vincitore, poi ne recupera la proposta."""
        if not proposals:
            return None
        # costruisce la richiesta A2A dal contratto del pipeline
        req = TaskRequest(
            task_id=task.task_id,
            task_type=task.capability,
            payload=task.request,
            max_cost=task.max_cost,
            requester_id="pipeline",
        )
        result = negotiate(self.registry, req)
        if not result.accepted or result.agent_id is None:
            return None
        # recupera la proposta dell'agente vincitore tra i candidati
        for p in proposals:
            if p.agent_id == result.agent_id:
                return p
        # nessuna proposta per l'agente vincitore -> nessun match
        return None


def guard_violation_detail(guard: NeurosymbolicGuard) -> str:
    if guard.violations:
        return guard.violations[-1].message
    return "na"


# --------------------------------------------------------------------------- #
# Toy env reale per l'integrazione (riusa la fisica dell'oscillatore)
# --------------------------------------------------------------------------- #


class ToyOscillator2:
    """Versione dell'oscillatore comoda per l'end-to-end (stato = [pos, vel])."""

    def __init__(self, A: float = -2.5, B: float = 0.4, dt: float = 0.1):
        self.A, self.B, self.dt = A, B, dt

    def step(self, state, action):
        x, v = state
        a = self.A * x - self.B * v + action
        return [x + v * self.dt, v + a * self.dt]


if __name__ == "__main__":
    torch.manual_seed(0)
    pipe = CascadePipeline()
    # registra un agente capace di "controllo"
    from a2a_protocol import generate_keypair
    _, pub = generate_keypair()
    pipe.register_agent(AgentManifest("ctrl-1", pub, ["controllo"], 0.1, 0.9))

    task = Task("t1", "controllo", {"pos": 0.5, "vel": 0.3}, max_cost=1.0)
    proposals = [
        AgentSignal("ctrl-1", {"action": 1.2}, confidence=0.96, capability="controllo"),
    ]
    dec = pipe.run(task, proposals, state=[0.5, 0.3], noise=False)
    print("approvato:", dec.approved,
          "| certificato:", dec.certified,
          "| output:", dec.final_output)
    print("controfattuale:", dec.evidence.counterfactuals if dec.evidence else None)
