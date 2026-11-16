"""Synthetic data for Cairn, a fictional outdoor retailer.

The agent's answers are computed from these tables, so the numbers in the
text, the charts, and the canvas always agree. Last week has three stories in
the West: the Summit down jacket sold out online, a wholesale order slipped a
week, and a new trail runner launched. Replace these functions with queries
against your warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

REGIONS = ["West", "Central", "East"]
CHANNELS = ["Online", "Stores", "Wholesale"]
CATEGORIES = ["Outerwear", "Footwear", "Camping", "Packs", "Accessories"]
WEEKS = 12

# Weekly net revenue per channel in the West, in dollars, and each category's
# share of it. The other regions are scaled copies with their own noise.
WEST_CHANNEL_BASE = {"Online": 760_000, "Stores": 880_000, "Wholesale": 540_000}
CATEGORY_SHARE = {
    "Online": [0.44, 0.18, 0.14, 0.14, 0.10],
    "Stores": [0.36, 0.22, 0.18, 0.12, 0.12],
    "Wholesale": [0.30, 0.14, 0.34, 0.16, 0.06],
}
REGION_SCALE = {"West": 1.0, "Central": 0.74, "East": 1.18}
AVERAGE_ORDER = {"Online": 142.0, "Stores": 96.0, "Wholesale": 2_850.0}
GROSS_MARGIN = {
    "Outerwear": 0.52,
    "Footwear": 0.47,
    "Camping": 0.44,
    "Packs": 0.50,
    "Accessories": 0.58,
}

# Last week's stories, as multipliers on the expected revenue of one cell.
STOCKOUT_CUT = 0.62  # Outerwear online in the West: the jacket sold out Tuesday
WHOLESALE_SLIP = 54_000  # Basecamp Outfitters' camping order moved a week
LAUNCH_LIFT = 0.11  # Footwear in the West: the Scree trail runner launched

SLIPPED_PO = "PO-48213"
WHOLESALE_ACCOUNT = "Basecamp Outfitters"
STOCKOUT_ITEM = "Summit down jacket"
STOCKOUT_DC = "Reno"
LAUNCH_ITEM = "Scree trail runner"


def week_starts(today: date | None = None) -> list[date]:
    """The Mondays of the last ``WEEKS`` full weeks, oldest first."""
    today = today or date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    return [last_monday - timedelta(weeks=WEEKS - 1 - i) for i in range(WEEKS)]


def week_label(start: date) -> str:
    return f"{start:%b} {start.day}"


def weekly_revenue() -> pd.DataFrame:
    """Net revenue and orders per week, region, channel, and category."""
    return _weekly_revenue(date.today())


@st.cache_data(max_entries=2)
def _weekly_revenue(today: date) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    weeks = week_starts(today)
    rows = []
    for region in REGIONS:
        for channel in CHANNELS:
            base = WEST_CHANNEL_BASE[channel] * REGION_SCALE[region]
            for category, share in zip(
                CATEGORIES, CATEGORY_SHARE[channel], strict=True
            ):
                # A gentle autumn ramp for outerwear, flat for everything else.
                ramp = 0.018 if category == "Outerwear" else 0.004
                for i, week in enumerate(weeks):
                    value = base * share * (1 + ramp * i) * rng.normal(1, 0.025)
                    rows.append((week, region, channel, category, value))
    data = pd.DataFrame(
        rows, columns=["week", "region", "channel", "category", "net_revenue"]
    )

    last = data["week"] == weeks[-1]
    west = data["region"] == "West"
    stockout = (
        last & west & (data["channel"] == "Online") & (data["category"] == "Outerwear")
    )
    data.loc[stockout, "net_revenue"] *= STOCKOUT_CUT
    slip = (
        last & west & (data["channel"] == "Wholesale") & (data["category"] == "Camping")
    )
    data.loc[slip, "net_revenue"] -= WHOLESALE_SLIP
    launch = (
        last
        & west
        & (data["category"] == "Footwear")
        & (data["channel"] != "Wholesale")
    )
    data.loc[launch, "net_revenue"] *= 1 + LAUNCH_LIFT

    data["net_revenue"] = data["net_revenue"].round(-2)
    data["orders"] = (data["net_revenue"] / data["channel"].map(AVERAGE_ORDER)).round()
    data["gross_margin"] = (
        data["net_revenue"] * data["category"].map(GROSS_MARGIN)
    ).round(-2)
    return data


@dataclass(frozen=True)
class Driver:
    label: str
    detail: str
    change: float


@dataclass(frozen=True)
class RevenueChange:
    """Last week against the week before, for one region."""

    region: str
    week: date
    previous_week: date
    revenue: float
    previous_revenue: float
    orders: float
    previous_orders: float
    drivers: list[Driver]
    by_cell: pd.DataFrame  # One row per channel and category, with the change
    trend: pd.DataFrame  # Weekly revenue per channel

    @property
    def change(self) -> float:
        return self.revenue - self.previous_revenue

    @property
    def change_pct(self) -> float:
        return self.change / self.previous_revenue

    @property
    def average_order(self) -> float:
        return self.revenue / self.orders

    @property
    def previous_average_order(self) -> float:
        return self.previous_revenue / self.previous_orders


def revenue_change(region: str = "West") -> RevenueChange:
    data = weekly_revenue()
    weeks = sorted(data["week"].unique())
    previous_week, week = weeks[-2], weeks[-1]
    regional = data[data["region"] == region]

    cells = regional[regional["week"].isin([previous_week, week])].pivot_table(
        index=["channel", "category"],
        columns="week",
        values="net_revenue",
        aggfunc="sum",
    )
    cells.columns = ["previous", "last"]
    cells["change"] = cells["last"] - cells["previous"]
    cells["change_pct"] = cells["change"] / cells["previous"]
    cells = cells.reset_index().sort_values("change")

    def cell(channel: str, category: str) -> float:
        row = cells[(cells["channel"] == channel) & (cells["category"] == category)]
        return float(row["change"].sum())

    stockout = cell("Online", "Outerwear")
    slip = cell("Wholesale", "Camping")
    launch = cell("Online", "Footwear") + cell("Stores", "Footwear")
    total = float(cells["change"].sum())
    drivers = [
        Driver("Outerwear online", f"{STOCKOUT_ITEM} sold out", stockout),
        Driver("Wholesale camping", f"{WHOLESALE_ACCOUNT} order moved a week", slip),
        Driver("Footwear", f"{LAUNCH_ITEM} launch", launch),
        Driver(
            "Everything else",
            "Within normal weekly range",
            total - stockout - slip - launch,
        ),
    ]

    totals = regional.groupby("week")[["net_revenue", "orders"]].sum()
    trend = regional.pivot_table(
        index="week", columns="channel", values="net_revenue", aggfunc="sum"
    )[CHANNELS].reset_index()
    return RevenueChange(
        region=region,
        week=week,
        previous_week=previous_week,
        revenue=float(totals.loc[week, "net_revenue"]),
        previous_revenue=float(totals.loc[previous_week, "net_revenue"]),
        orders=float(totals.loc[week, "orders"]),
        previous_orders=float(totals.loc[previous_week, "orders"]),
        drivers=drivers,
        by_cell=cells,
        trend=trend,
    )


@dataclass(frozen=True)
class Kpi:
    label: str
    value: float
    previous: float
    history: list[float]
    plan: float
    kind: str  # "money", "count", or "percent"


def company_kpis() -> list[Kpi]:
    """Company-wide KPIs for last week, with 12 weeks of history and the plan."""
    data = weekly_revenue()
    weekly = data.groupby("week")[["net_revenue", "orders", "gross_margin"]].sum()
    revenue = weekly["net_revenue"]
    orders = weekly["orders"]
    margin = weekly["gross_margin"] / weekly["net_revenue"]
    average_order = revenue / orders

    def kpi(label: str, series: pd.Series, plan_factor: float, kind: str) -> Kpi:
        history = [float(v) for v in series]
        return Kpi(
            label, history[-1], history[-2], history, history[-2] * plan_factor, kind
        )

    return [
        kpi("Net revenue", revenue, 1.02, "money"),
        kpi("Orders", orders, 1.015, "count"),
        kpi("Average order", average_order, 1.0, "money"),
        kpi("Gross margin", margin, 1.0, "percent"),
    ]


@dataclass(frozen=True)
class Product:
    name: str
    price: float
    unit_cost: float
    weekly_demand: float  # Units per week at the current price
    elasticity: float
    elasticity_sd: float


JACKET = Product(
    name=STOCKOUT_ITEM,
    price=249.0,
    unit_cost=112.0,
    weekly_demand=410.0,
    elasticity=-1.6,
    elasticity_sd=0.25,
)

# Units available per week: the Reno restock lands in week 2.
JACKET_SUPPLY = [180, 640, 640, 640, 640, 640, 640, 640]


def stock_positions() -> pd.DataFrame:
    """Items at risk of stocking out in the next two weeks, per distribution center."""
    rows = [
        # item, category, dc, on_hand, on_order, weekly_forecast, case_pack, unit_cost, lead_days, supplier, confidence, new_supplier
        (
            STOCKOUT_ITEM,
            "Outerwear",
            "Reno",
            0,
            0,
            410,
            12,
            112.0,
            9,
            "Northline Apparel",
            0.92,
            False,
        ),
        (
            STOCKOUT_ITEM,
            "Outerwear",
            "Columbus",
            340,
            0,
            265,
            12,
            112.0,
            9,
            "Northline Apparel",
            0.88,
            False,
        ),
        (
            "Ridgeline rain shell",
            "Outerwear",
            "Allentown",
            210,
            120,
            180,
            12,
            74.0,
            12,
            "Northline Apparel",
            0.84,
            False,
        ),
        (
            "Ember sleeping bag",
            "Camping",
            "Reno",
            95,
            0,
            72,
            6,
            88.0,
            14,
            "Kestrel Outdoor",
            0.71,
            True,
        ),
        (
            "Daybreak 24L daypack",
            "Packs",
            "Columbus",
            160,
            0,
            118,
            10,
            38.0,
            10,
            "Fernway Goods",
            0.86,
            False,
        ),
        (
            "Talus hiking boot",
            "Footwear",
            "Reno",
            132,
            48,
            104,
            8,
            61.0,
            11,
            "Granite Footwear",
            0.8,
            False,
        ),
    ]
    columns = [
        "item", "category", "dc", "on_hand", "on_order", "weekly_forecast", "case_pack",
        "unit_cost", "lead_days", "supplier", "confidence", "new_supplier",
    ]  # fmt: skip
    return pd.DataFrame(rows, columns=columns)
