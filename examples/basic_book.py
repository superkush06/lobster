"""Basic order book demo - add, cancel, match."""

from lobster.book import OrderBook
from lobster.matching import match
from lobster.order import Order, OrderType, Side


def main() -> None:
    book = OrderBook()

    # Build some depth
    for p in (99.0, 99.5, 99.8):
        book.add(Order(Side.BUY, qty=10, price=p))
    for p in (100.2, 100.5, 101.0):
        book.add(Order(Side.SELL, qty=10, price=p))

    print("Initial book")
    for line in _format(book):
        print(line)

    print("\nIncoming marketable buy of 15...")
    trades = match(book, Order(Side.BUY, qty=15, type=OrderType.MARKET))
    for t in trades:
        print(f"  trade: {t.qty} @ {t.price}")

    print("\nBook after sweep")
    for line in _format(book):
        print(line)


def _format(book: OrderBook) -> list[str]:
    out = ["  asks (best on top):"]
    for p, q in reversed(book.depth(Side.SELL, 5)):
        out.append(f"    {p:>7.2f}  x {q}")
    out.append(f"  --- mid={book.mid} spread={book.spread} ---")
    out.append("  bids (best on top):")
    for p, q in book.depth(Side.BUY, 5):
        out.append(f"    {p:>7.2f}  x {q}")
    return out


if __name__ == "__main__":
    main()
