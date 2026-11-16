"""A Monte Carlo price simulation for one product, in plain NumPy.

The agent calls ``simulate`` for each price it compares, and the canvas shows
this function's source, so what people read is what ran.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from utils.data import JACKET, JACKET_SUPPLY, Product

RUNS = 2_000
WEEKS = len(JACKET_SUPPLY)


@dataclass(frozen=True)
class Outcome:
    price: float
    label: str
    units: np.ndarray  # Units sold per run and week, shape (RUNS, WEEKS)
    demand: np.ndarray  # Units people wanted, same shape
    margin: np.ndarray  # Gross margin per run, over all weeks

    def p(self, q: float, values: np.ndarray | None = None) -> float:
        return float(np.percentile(self.margin if values is None else values, q))

    @property
    def units_sold(self) -> float:
        return float(np.median(self.units.sum(axis=1)))

    @property
    def lost_units(self) -> float:
        return float(np.median((self.demand - self.units).sum(axis=1)))


def simulate(
    product: Product, price: float, supply: list[int], seed: int = 7
) -> tuple[np.ndarray, np.ndarray]:
    """Units sold and units demanded per run and week at ``price``.

    Demand follows a constant-elasticity curve with an uncertain elasticity,
    and weekly noise. Sales can't exceed the units available that week.
    """
    rng = np.random.default_rng(seed)  # The same futures for every price
    elasticity = rng.normal(product.elasticity, product.elasticity_sd, size=(RUNS, 1))
    noise = rng.lognormal(mean=0, sigma=0.16, size=(RUNS, len(supply)))
    demand = product.weekly_demand * (price / product.price) ** elasticity * noise
    sold = np.minimum(demand, np.array(supply))
    return sold, demand


def compare(changes: tuple[float, ...] = (-0.10, 0.0, 0.10)) -> list[Outcome]:
    """Simulate the product at its current price and at each relative change."""
    outcomes = []
    for change in changes:
        price = round(JACKET.price * (1 + change))
        units, demand = simulate(JACKET, price, JACKET_SUPPLY)
        margin = (units * (price - JACKET.unit_cost)).sum(axis=1)
        label = "Current price" if change == 0 else f"{change:+.0%}"
        outcomes.append(Outcome(price, label, units, demand, margin))
    return outcomes
