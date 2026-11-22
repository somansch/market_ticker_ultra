"""What is held of an instrument, worked out from its purchases.

An instrument can carry any number of purchases - each a quantity, the
price paid per unit in the instrument's own currency, and optionally the
day. A negative quantity is a sale. From them comes what is held now and
what it cost, by the average-cost method: a sale takes units out at the
average price paid so far, so the cost of what remains stays the average.

A purchase or a sale can also carry what it cost to make: fees and taxes.
They change neither what is held nor its average price; they are added up
beside the gains a sale realised (see Ledger).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers import Quote

CONF_LOTS = "lots"
LOT_QUANTITY = "quantity"
LOT_PRICE = "price"
LOT_DATE = "date"
LOT_FEES = "fees"
LOT_TAXES = "taxes"


@dataclass(frozen=True, slots=True)
class Holding:
    """What is held of one instrument: how much, and what it cost."""

    quantity: float
    cost: float

    @property
    def average_price(self) -> float | None:
        return self.cost / self.quantity if self.quantity else None


@dataclass(frozen=True, slots=True)
class Position:
    """A holding at a price: what it is worth, and how it has done."""

    quantity: float
    cost: float
    value: float
    day_change: float | None
    gain: float
    gain_percent: float | None


@dataclass(frozen=True, slots=True)
class Ledger:
    """What the sales of an instrument realised, and what was paid in fees
    and taxes over all its purchases and sales."""

    realized: float
    fees: float
    taxes: float

    @property
    def empty(self) -> bool:
        return not (self.realized or self.fees or self.taxes)


def _amount(value: Any) -> float:
    """A fee or a tax as stored: a figure that is not negative, else none."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    return amount if amount > 0 else 0.0


def clean_lots(raw: Any) -> list[dict[str, Any]]:
    """The purchases as stored, without anything that is not one."""
    lots = []
    for item in raw or []:
        try:
            quantity = float(item[LOT_QUANTITY])
            price = float(item[LOT_PRICE])
        except (KeyError, TypeError, ValueError):
            continue
        if not quantity or price < 0:
            continue
        lot = {LOT_QUANTITY: quantity, LOT_PRICE: price, LOT_DATE: item.get(LOT_DATE) or None}
        # Kept only where there are any: most purchases have neither.
        for key in (LOT_FEES, LOT_TAXES):
            amount = _amount(item.get(key))
            if amount:
                lot[key] = amount
        lots.append(lot)
    return lots


def in_order(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """In the order of their days. Without a day a purchase counts first -
    it was always there - and a sale last, or it would find nothing to take
    from; among themselves in the order they were entered."""

    def place(pair: tuple[int, dict[str, Any]]) -> tuple[int, str, int]:
        index, lot = pair
        day = lot[LOT_DATE] or ""
        return (1 if day else 0 if lot[LOT_QUANTITY] > 0 else 2, day, index)

    return [lot for _, lot in sorted(enumerate(lots), key=place)]


def ledger_from_lots(raw: Any) -> Ledger:
    """What the sales realised - each against the average price paid until
    then - and the fees and taxes of every purchase and sale."""
    quantity = cost = realized = fees = taxes = 0.0
    for lot in in_order(clean_lots(raw)):
        fees += lot.get(LOT_FEES, 0.0)
        taxes += lot.get(LOT_TAXES, 0.0)
        amount = lot[LOT_QUANTITY]
        if amount > 0:
            quantity += amount
            cost += amount * lot[LOT_PRICE]
            continue
        sold = min(-amount, quantity)
        if quantity > 0:
            average = cost / quantity
            realized += sold * (lot[LOT_PRICE] - average)
            cost -= sold * average
        quantity -= sold
    return Ledger(realized=round(realized, 6), fees=round(fees, 6), taxes=round(taxes, 6))


def holding_from_lots(raw: Any) -> Holding | None:
    """What the purchases add up to - None where nothing is held.

    In the order in_order() puts them in: a sale can only take from what
    was bought before it.
    """
    lots = clean_lots(raw)
    if not lots:
        return None
    quantity = 0.0
    cost = 0.0
    for lot in in_order(lots):
        amount = lot[LOT_QUANTITY]
        if amount > 0:
            quantity += amount
            cost += amount * lot[LOT_PRICE]
            continue
        sold = min(-amount, quantity)
        if quantity > 0:
            cost -= sold * (cost / quantity)
        quantity -= sold
    # What a sum of tenths leaves behind is not a holding.
    if quantity < 1e-9:
        return None
    return Holding(quantity=round(quantity, 8), cost=round(max(cost, 0.0), 6))


def position_at(holding: Holding, quote: Quote) -> Position:
    """The holding at the instrument's current quote."""
    value = holding.quantity * quote.price
    gain = value - holding.cost
    change = quote.change
    return Position(
        quantity=holding.quantity,
        cost=holding.cost,
        value=value,
        day_change=None if change is None else holding.quantity * change,
        gain=gain,
        gain_percent=gain / holding.cost * 100 if holding.cost else None,
    )
