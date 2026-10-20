# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""A parcel service, with the duplication a hurried week leaves behind.

Nothing imports this file: it is here to be read, and to be found duplicated. The
reports beside it are what Clone Digger writes on it, in its four formats.
"""

from dataclasses import dataclass

EXPRESS_RATE = 4.50
STANDARD_RATE = 1.75


@dataclass
class Parcel:
    """A parcel to carry, as the carrier's file describes it."""

    code: str
    weight: float
    express: bool
    discount: float = 0.0


@dataclass
class Pallet:
    """A pallet to carry, taller than it is heavy."""

    code: str
    height: float
    stackable: bool


def express_cost(parcels: list[Parcel]) -> float:
    """What the parcels carried overnight cost, to the cent."""
    total = 0.0
    for parcel in parcels:
        price = parcel.weight * EXPRESS_RATE
        if parcel.discount:
            price = price - parcel.discount
        total = total + price
    return round(total, 2)


def standard_cost(parcels: list[Parcel]) -> float:
    """What the parcels carried in a week cost, to the cent."""
    amount = 0.0
    for parcel in parcels:
        cost = parcel.weight * STANDARD_RATE
        if parcel.discount:
            cost = cost - parcel.discount
        amount = amount + cost
    return round(amount, 2)


def parcel_from_row(row: dict[str, str]) -> Parcel:
    """Read a parcel from a row of the carrier's file."""
    code = row["code"].strip().upper()
    if not code:
        raise ValueError(f"a row without a code: {row}")
    weight = float(row.get("weight", "0"))
    return Parcel(code, weight, row.get("express") == "yes")


def pallet_from_row(row: dict[str, str]) -> Pallet:
    """Read a pallet from a row of the carrier's file."""
    code = row["code"].strip().upper()
    if not code:
        raise ValueError(f"a row without a code: {row}")
    height = float(row.get("height", "0"))
    return Pallet(code, height, row.get("stackable") == "yes")
