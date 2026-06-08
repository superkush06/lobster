import math

import pytest

from lobster.impact import LinearImpact, SquareRootImpact


def test_linear_monotonic_in_size():
    m = LinearImpact(eta=0.01)
    assert m.impact(+1, 10) < m.impact(+1, 20) < m.impact(+1, 50)


def test_linear_sign():
    m = LinearImpact(eta=0.01)
    assert m.impact(+1, 10) > 0
    assert m.impact(-1, 10) < 0


def test_sqrt_scaling():
    m = SquareRootImpact(eta=0.1, daily_volume=1_000_000)
    i_1 = m.impact(+1, 100)
    i_4 = m.impact(+1, 400)
    # Doubling size in sqrt model: impact ratio should be ~2 (since sqrt(4)=2)
    assert math.isclose(i_4 / i_1, 2.0, rel_tol=1e-9)


def test_invalid_params():
    with pytest.raises(ValueError):
        LinearImpact(eta=-1)
    with pytest.raises(ValueError):
        SquareRootImpact(eta=-1)
    with pytest.raises(ValueError):
        SquareRootImpact(daily_volume=0)
