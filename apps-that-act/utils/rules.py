"""Guardrails for Cairn Reorder desk: risk flags, low-risk proposals, and validation.

Every check runs on the server before anything is written. The table's
column limits only help people enter valid values; these rules decide.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from utils import store

FLAGS = ["Over cap", "Low confidence", "New supplier", "Demand spike", "Due today"]


def money(value: float) -> str:
    if abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    if abs(value) >= 1e4:
        return f"${value / 1e3:.0f}k"
    return f"${value:,.0f}"


def enrich(proposals: pd.DataFrame, policies: pd.DataFrame) -> pd.DataFrame:
    """Add value, days to stockout, risk flags, and the low-risk mark."""
    frame = proposals.copy()
    policy = policies.loc[frame["category"]].set_axis(frame.index)
    today = date.today()
    frame["value"] = frame["proposed_qty"] * frame["unit_cost"]
    frame["days_to_stockout"] = (
        (frame["on_hand"] + frame["on_order"]) / (frame["weekly_forecast"] / 7)
    ).round()
    frame["arrives"] = pd.Timestamp(today) + pd.to_timedelta(
        frame["lead_time_days"], unit="D"
    )
    frame["stockout_date"] = pd.Timestamp(today) + pd.to_timedelta(
        frame["days_to_stockout"], unit="D"
    )
    checks = {
        "Over cap": frame["value"] > policy["order_cap"],
        "Low confidence": frame["confidence"] * 100 < policy["min_confidence"],
        "New supplier": frame["new_supplier"].astype(bool),
        "Demand spike": frame["demand_spike"].astype(bool),
        "Due today": frame["cutoff"].dt.date == today,
    }
    frame["flags"] = [
        [flag for flag in FLAGS if checks[flag].loc[proposal]]
        for proposal in frame.index
    ]
    frame["low_risk"] = (
        (frame["value"] <= policy["auto_approve_limit"])
        & ~checks["Over cap"]
        & ~checks["Low confidence"]
        & ~checks["New supplier"]
        & ~checks["Demand spike"]
    )
    return frame


def validate(
    decision: store.Decision, proposal: pd.Series, policies: pd.DataFrame
) -> str | None:
    """Why ``decision`` can't be written, or ``None`` when it can."""
    policy = policies.loc[proposal["category"]]
    if decision.action == "reject":
        return None if decision.note.strip() else "Add a note to reject"
    if decision.action == "hold":
        return None
    quantity = decision.final_qty
    if quantity <= 0:
        return "Order at least one case, or reject the proposal"
    if quantity % proposal["case_pack"]:
        return f"Order whole cases of {proposal['case_pack']}"
    value = quantity * proposal["unit_cost"]
    if value > policy["order_cap"]:
        return (
            f"{money(value)} is over the {proposal['category'].lower()} order cap "
            f"of {money(policy['order_cap'])}"
        )
    change = abs(quantity / proposal["proposed_qty"] - 1) * 100
    if change > policy["max_change_pct"] and not decision.note.strip():
        return f"Add a note for a change over {policy['max_change_pct']:.0f}%"
    return None


def acceptance(decisions: pd.DataFrame) -> float:
    """Share of decisions that approved the agent's proposal unchanged."""
    if decisions.empty:
        return float("nan")
    return float(np.mean(decisions["action"] == "Approved"))
