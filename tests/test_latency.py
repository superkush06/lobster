import random
from statistics import mean

import pytest

from lobster.latency import ConstantLatency, JitteredLatency


def test_constant():
    lm = ConstantLatency(5.0)
    rng = random.Random(0)
    assert all(lm.sample(rng) == 5.0 for _ in range(10))


def test_jittered_mean_approx():
    lm = JitteredLatency(mean=4.0, shape=2.0)
    rng = random.Random(42)
    samples = [lm.sample(rng) for _ in range(5000)]
    # Tolerate ~5% deviation
    assert abs(mean(samples) - 4.0) < 0.4


def test_invalid_params():
    with pytest.raises(ValueError):
        ConstantLatency(-1.0)
    with pytest.raises(ValueError):
        JitteredLatency(mean=0)
    with pytest.raises(ValueError):
        JitteredLatency(mean=1, shape=-1)
