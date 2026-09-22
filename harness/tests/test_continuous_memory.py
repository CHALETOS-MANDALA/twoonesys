"""Test della Memoria Continua (Layer 2)."""

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn  # noqa: E402

from cascade.continuous_memory import (
    EWC,
    ProgressiveNet,
    SelectiveReplayBuffer,
)


def test_ewc_penalty_is_zero_without_snapshot():
    model = nn.Linear(4, 2)
    ewc = EWC(model, lambda_ewc=10.0)
    assert ewc.penalty().item() == 0.0


def test_ewc_penalty_grows_with_distance():
    model = nn.Linear(4, 2)
    ewc = EWC(model, lambda_ewc=10.0)
    loader = _loader(torch.randn(8, 4), torch.randint(0, 2, (8,)))
    ewc.snapshot_task(loader, nn.CrossEntropyLoss())
    p0 = ewc.penalty().item()
    assert p0 == pytest.approx(0.0, abs=1e-6)
    # spostiamo un peso
    with torch.no_grad():
        model.weight.data.add_(0.5)
    p1 = ewc.penalty().item()
    assert p1 > 0


def test_selective_buffer_cap():
    buf = SelectiveReplayBuffer(capacity=10)
    x = torch.randn(20, 4)
    y = torch.zeros(20, dtype=torch.long)
    for i in range(30):
        buf.add(x[i % 20], y[i % 20])
    assert len(buf) <= 10


def test_selective_buffer_sample_returns_batch():
    buf = SelectiveReplayBuffer(capacity=10)
    for i in range(10):
        buf.add(torch.randn(4), torch.tensor(0))
    bx, by = buf.sample(4)
    assert bx.shape == (4, 4)


def test_progressive_net_can_add_tasks():
    net = ProgressiveNet(input_dim=5, hidden_dim=8, output_dim=2)
    assert net.add_task() == 0
    assert net.add_task() == 1
    x = torch.randn(3, 5)
    out = net(x, task_id=1)
    assert out.shape == (3, 2)


def test_progressive_net_forward_shapes():
    net = ProgressiveNet(input_dim=5, hidden_dim=8, output_dim=3)
    net.add_task()
    net.add_task()
    out = net(torch.randn(2, 5), task_id=1)
    assert out.shape == (2, 3)


def _loader(xs, ys, batch=4):
    return torch.utils.data.DataLoader(
        list(zip(xs, ys)), batch_size=batch, shuffle=True
    )
