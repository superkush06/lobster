import pytest
from lobster.order import Order, Side, OrderType


def test_buy_order_basic():
    o = Order(Side.BUY, qty=10, price=100.0)
    assert o.is_buy
    assert o.qty == 10
    assert o.price == 100.0
    assert o.type is OrderType.LIMIT


def test_market_order_no_price():
    o = Order(Side.SELL, qty=5, type=OrderType.MARKET)
    assert o.price is None


def test_limit_requires_price():
    with pytest.raises(ValueError, match="requires a price"):
        Order(Side.BUY, qty=5)


def test_market_forbids_price():
    with pytest.raises(ValueError, match="must not specify"):
        Order(Side.SELL, qty=5, price=99.0, type=OrderType.MARKET)


def test_invalid_qty():
    with pytest.raises(ValueError, match="qty must be positive"):
        Order(Side.BUY, qty=0, price=100.0)


def test_unique_ids():
    a = Order(Side.BUY, qty=1, price=100.0)
    b = Order(Side.BUY, qty=1, price=100.0)
    assert a.id != b.id


def test_fill_reduces_qty():
    o = Order(Side.BUY, qty=10, price=100.0)
    o.fill(3)
    assert o.qty == 7


def test_fill_invalid():
    o = Order(Side.BUY, qty=5, price=100.0)
    with pytest.raises(ValueError):
        o.fill(0)
    with pytest.raises(ValueError):
        o.fill(10)


def test_side_opposite():
    assert Side.BUY.opposite is Side.SELL
    assert Side.SELL.opposite is Side.BUY
