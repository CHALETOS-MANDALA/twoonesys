"""Test del World Model JEPA (Layer 3)."""

import pytest

torch = pytest.importorskip("torch")

from cascade.world_model import (
    JEPAWorldModel,
    ToyOscillator,
    VicregLoss,
    train_world_model,
)


def test_forward_shapes():
    m = JEPAWorldModel(obs_dim=4, action_dim=2, latent_dim=16)
    obs = torch.randn(8, 4)
    act = torch.randn(8, 2)
    obsn = torch.randn(8, 4)
    loss, zp, zt = m(obs, act, obsn)
    assert zp.shape == (8, 16)
    assert zt.shape == (8, 16)
    assert loss.ndim == 0


def test_target_encoder_momentum_updates():
    m = JEPAWorldModel(obs_dim=3, action_dim=1, latent_dim=8)
    before = [p.clone() for p in m.target_encoder.parameters()]
    # sposta il context encoder
    with torch.no_grad():
        for p in m.context_encoder.parameters():
            p.add_(0.1)
    m.update_target_network()
    moved = False
    for b, a in zip(before, m.target_encoder.parameters()):
        if not torch.allclose(b, a):
            moved = True
    assert moved  # il target segue (parzialmente) il context


def test_target_encoder_frozen():
    m = JEPAWorldModel(obs_dim=3, action_dim=1, latent_dim=8)
    all_frozen = all(not p.requires_grad for p in m.target_encoder.parameters())
    assert all_frozen


def test_oscillator_dynamics():
    env = ToyOscillator(A=-2.5, B=0.4, dt=0.1)
    s = torch.tensor([[1.0, 0.0]])
    a = torch.tensor([[0.0]])
    nxt = env.step(s, a)
    # posizione aumenta (v=0 -> x'=x), velocita' diventa negativa (A<0)
    assert nxt[0, 0].item() > 0.99
    assert nxt[0, 1].item() < 0.0


def test_world_model_learns():
    torch.manual_seed(0)
    env = ToyOscillator(mu=0.05)
    dataset = env.make_dataset(n_traj=25, len_traj=20, seed=0)
    m = JEPAWorldModel(obs_dim=2, action_dim=1, latent_dim=16, momentum=0.995)
    losses = train_world_model(m, dataset, epochs=30, batch_size=32)
    assert len(losses) == 30
    # la loss latente deve diminuire (apprendimento)
    assert losses[-1] < losses[0]
    # deve convergere sotto la iniziale
    assert losses[-1] < losses[0] * 0.9


def test_predict_latent_single_state():
    torch.manual_seed(0)
    env = ToyOscillator()
    dataset = env.make_dataset(n_traj=10, len_traj=10)
    m = JEPAWorldModel(obs_dim=2, action_dim=1, latent_dim=16)
    train_world_model(m, dataset, epochs=5)
    z = m.predict_latent(torch.tensor([[0.5, 0.2]]), torch.tensor([[0.3]]))
    assert z.shape == (1, 16)
