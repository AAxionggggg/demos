"""Synthetic proposals and decision history for Cairn Reorder desk.

The replenishment agent runs every morning. For each SKU and distribution
center that will run short, it proposes a purchase order and explains how it
sized it. Here the agent's output is generated: replace ``proposals`` with
the rows your own agent or planning job writes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np

AGENT_RUN = time(5, 12)
TARGET_COVER_WEEKS = 6
LOCATIONS = ["Reno DC", "Columbus DC", "Allentown DC"]
CATEGORIES = ["Outerwear", "Footwear", "Camping", "Packs", "Accessories"]
PRIORITIES = ["Critical", "High", "Normal"]
REVIEWERS = ["Maya Lin", "Omar Haddad", "Jess Park", "Tomás Ruiz"]


@dataclass(frozen=True)
class Item:
    sku: str
    product: str
    category: str
    unit_cost: float
    case_pack: int
    weekly_units: float  # Typical weekly demand per distribution center now
    season_driver: str


@dataclass(frozen=True)
class Supplier:
    name: str
    lead_time_days: int
    on_time: float
    new: bool = False


ITEMS = [
    Item(
        "OW-1042", "Summit insulated jacket", "Outerwear", 96, 24, 340, "holiday peak"
    ),
    Item("OW-1108", "Ridge rain shell", "Outerwear", 58, 24, 180, "steady demand"),
    Item("OW-1215", "Fjell down vest", "Outerwear", 44, 36, 210, "holiday peak"),
    Item("OW-1330", "Trailhead fleece", "Outerwear", 31, 48, 260, "cold snap"),
    Item("FW-2051", "Talus hiking boot", "Footwear", 71, 12, 150, "holiday peak"),
    Item("FW-2120", "Basecamp winter boot", "Footwear", 84, 12, 190, "cold snap"),
    Item("FW-2204", "Scree trail runner", "Footwear", 52, 12, 90, "off-season"),
    Item("CP-3017", "Ultralight 2P tent", "Camping", 138, 6, 40, "off-season"),
    Item("CP-3140", "Ember sleeping bag", "Camping", 64, 8, 85, "holiday gifting"),
    Item("CP-3222", "Trail stove kit", "Camping", 29, 24, 70, "holiday gifting"),
    Item("PK-4008", "Daybreak 24L daypack", "Packs", 38, 20, 120, "steady demand"),
    Item("PK-4113", "Traverse 55L pack", "Packs", 87, 10, 45, "off-season"),
    Item("AC-5021", "Merino beanie", "Accessories", 9, 96, 520, "cold snap"),
    Item("AC-5107", "Trekking poles", "Accessories", 22, 24, 95, "holiday gifting"),
    Item("AC-5230", "Headlamp 400 lm", "Accessories", 14, 48, 240, "holiday gifting"),
]
SUPPLIERS = {
    "Outerwear": [Supplier("Northline Textiles", 18, 0.94), Supplier("Alder & Pine Mfg", 24, 0.88)],
    "Footwear": [Supplier("Granite Peak Supply", 21, 0.91), Supplier("Bluewater Trading", 14, 0.0, new=True)],
    "Camping": [Supplier("Alder & Pine Mfg", 24, 0.88), Supplier("Summit Gear Works", 16, 0.96)],
    "Packs": [Supplier("Summit Gear Works", 16, 0.96)],
    "Accessories": [Supplier("Granite Peak Supply", 12, 0.91), Supplier("Bluewater Trading", 10, 0.0, new=True)],
}  # fmt: skip
DEFAULT_POLICIES = {
    # category: (auto-approve limit $, order cap $, max quantity change %, min confidence %)
    "Outerwear": (15_000, 120_000, 25, 85),
    "Footwear": (12_000, 90_000, 25, 85),
    "Camping": (10_000, 60_000, 30, 80),
    "Packs": (8_000, 50_000, 30, 80),
    "Accessories": (6_000, 30_000, 40, 80),
}


def _proposal(
    rng: np.random.Generator, index: int, item: Item, location: str, today: date
) -> dict[str, object]:
    supplier = SUPPLIERS[item.category][rng.integers(len(SUPPLIERS[item.category]))]
    location_factor = {"Reno DC": 0.8, "Columbus DC": 1.15, "Allentown DC": 1.0}[
        location
    ]
    spike = item.season_driver == "cold snap" and rng.random() < 0.6
    trend = (
        rng.normal(0.18, 0.12)
        if "peak" in item.season_driver
        else rng.normal(0.03, 0.08)
    )
    weekly = item.weekly_units * location_factor * (1 + trend) * (1.45 if spike else 1)
    history = (
        item.weekly_units
        * location_factor
        * np.linspace(0.75, 1.0 + trend, 12)
        * np.exp(rng.normal(0, 0.07, 12))
    )
    if spike:
        history[-1] *= 1.9
    forecast = weekly * np.linspace(
        1.0, 1.08 if "peak" in item.season_driver else 0.98, 6
    )
    weeks_on_hand = float(rng.uniform(1.2, 5.5))
    on_hand = int(weekly * weeks_on_hand)
    on_order = int(rng.choice([0, 0, 0, item.case_pack * int(rng.integers(2, 8))]))
    needed = TARGET_COVER_WEEKS * weekly - on_hand - on_order
    cases = max(1, math.ceil(needed / item.case_pack))
    proposed = cases * item.case_pack
    days_to_stockout = (on_hand + on_order) / (weekly / 7)
    lead = supplier.lead_time_days
    if days_to_stockout < lead - 2:
        priority = "Critical"
    elif days_to_stockout < lead + 10:
        priority = "High"
    else:
        priority = "Normal"
    confidence = float(np.clip(rng.normal(0.9, 0.05), 0.6, 0.99))
    if spike:
        confidence -= 0.15
    if supplier.new:
        confidence -= 0.08
    cutoff_days = {"Critical": 0, "High": 1, "Normal": int(rng.integers(2, 5))}[
        priority
    ]
    cutoff = datetime.combine(today + timedelta(days=cutoff_days), time(16, 0))
    previous = float(history[-5:-1].mean())
    reasoning = [
        (
            "Checked stock",
            f"{on_hand:,} units on hand at {location}"
            + (f" and {on_order:,} on order" if on_order else ", none on order")
            + f": about {days_to_stockout:.0f} days of demand.",
        ),
        (
            "Forecast demand",
            f"{weekly:,.0f} units a week over the next 4 weeks, "
            f"{weekly / previous - 1:+.0%} vs. the last 4 ({item.season_driver}).",
        ),
        (
            "Checked supplier",
            f"{supplier.name}: {lead}-day lead time, "
            + (
                "no delivery history yet (first order)."
                if supplier.new
                else f"{supplier.on_time:.0%} of orders on time over 90 days."
            ),
        ),
        (
            "Sized the order",
            f"{TARGET_COVER_WEEKS} weeks of cover minus stock and open orders, "
            f"rounded up to {cases} cases of {item.case_pack}.",
        ),
    ]
    if spike:
        reasoning.insert(
            2,
            (
                "Flagged a demand spike",
                f"Last week sold {history[-1] / previous:.1f}× the 4-week average. "
                "The forecast counts half of it, so check before approving.",
            ),
        )
    return {
        "id": f"PO-{26400 + index}",
        "created_at": datetime.combine(today, AGENT_RUN).isoformat(),
        "sku": item.sku,
        "product": item.product,
        "category": item.category,
        "location": location,
        "supplier": supplier.name,
        "new_supplier": int(supplier.new),
        "on_hand": on_hand,
        "on_order": on_order,
        "weekly_forecast": round(weekly, 1),
        "lead_time_days": lead,
        "case_pack": item.case_pack,
        "unit_cost": item.unit_cost,
        "proposed_qty": proposed,
        "confidence": round(confidence, 3),
        "priority": priority,
        "demand_spike": int(spike),
        "cutoff": cutoff.isoformat(),
        "reasoning": json.dumps(reasoning),
        "history": json.dumps([round(float(v)) for v in history]),
        "forecast": json.dumps([round(float(v)) for v in forecast]),
        "status": "pending",
        "final_qty": None,
        "decided_by": None,
        "decided_at": None,
        "note": None,
    }


def proposals(today: date) -> list[dict[str, object]]:
    """Today's agent run: one proposal per SKU and location that runs short."""
    rng = np.random.default_rng(today.toordinal())
    rows = []
    for item in ITEMS:
        for location in LOCATIONS:
            if rng.random() < 0.72:
                rows.append(_proposal(rng, len(rows), item, location, today))
    return rows


def decision_history(today: date, days: int = 30) -> list[dict[str, object]]:
    """Planner decisions on earlier agent runs, for the activity page."""
    rng = np.random.default_rng(today.toordinal() + 7)
    rows = []
    for day in range(days, 0, -1):
        run = datetime.combine(today - timedelta(days=day), AGENT_RUN)
        if run.weekday() >= 5:
            continue
        # Acceptance improves over the month as the agent's forecasts get tuned.
        accept = 0.62 + 0.18 * (days - day) / days
        for _ in range(int(rng.integers(9, 18))):
            item = ITEMS[rng.integers(len(ITEMS))]
            agent_qty = item.case_pack * int(rng.integers(3, 40))
            roll = rng.random()
            if roll < accept:
                action, final = "Approved", agent_qty
            elif roll < accept + 0.22:
                change = rng.choice([-1, 1]) * rng.uniform(0.1, 0.5)
                final = max(
                    item.case_pack,
                    round(agent_qty * (1 + change) / item.case_pack) * item.case_pack,
                )
                action = "Approved with changes"
            elif roll < accept + 0.31:
                action, final = "Rejected", 0
            else:
                action, final = "Held", agent_qty
            decided = run + timedelta(minutes=int(rng.integers(40, 9 * 60)))
            rows.append(
                {
                    "proposal_id": f"PO-{25000 + len(rows)}",
                    "decided_at": decided.isoformat(timespec="seconds"),
                    "reviewer": REVIEWERS[rng.integers(len(REVIEWERS))],
                    "action": action,
                    "product": item.product,
                    "category": item.category,
                    "location": LOCATIONS[rng.integers(len(LOCATIONS))],
                    "agent_qty": agent_qty,
                    "final_qty": final,
                    "value": final * item.unit_cost,
                    "note": _history_note(rng, action),
                }
            )
    return rows


def _history_note(rng: np.random.Generator, action: str) -> str | None:
    notes = {
        "Approved with changes": [
            "Trimmed to match the open PO from last week.",
            "Raised for the regional cold-weather promo.",
            "Rounded to a full pallet.",
            "Supplier capacity is limited this month.",
        ],
        "Rejected": [
            "Duplicate of a transfer from Columbus.",
            "Discontinued colorway, clearing stock instead.",
            "Spike was a one-off bulk order.",
        ],
        "Held": [
            "Waiting on the supplier's revised price.",
            "Check with merchandising.",
        ],
    }
    if action in notes:
        return str(rng.choice(notes[action]))
    return None
