"""ECharts options for Cairn Reorder desk."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

import streamlit as st


@dataclass(frozen=True)
class Palette:
    primary: str
    secondary: str
    warning: str
    muted: str
    text: str
    background: str
    band: str


_LIGHT = Palette(
    primary="#2563EB",
    secondary="#9333EA",
    warning="#D97706",
    muted="#94A3B8",
    text="#334155",
    background="#FFFFFF",
    band="#E5ECFD",
)
_DARK = Palette(
    primary="#4C82F7",
    secondary="#9467EA",
    warning="#F59E0B",
    muted="#475569",
    text="#C3CCDA",
    background="#0A0F1C",
    band="#162443",
)
# Decision outcomes are statuses, and they keep the same color on every chart
# and badge (see ui.ACTION_BADGES): approved green, edited blue, rejected amber.
ACTION_COLORS = {
    "Approved": ("#15803D", "#2FA36B"),
    "Approved with changes": ("#2563EB", "#4C82F7"),
    "Rejected": ("#D97706", "#E39A2D"),
    "Held": ("#94A3B8", "#475569"),
}


def palette() -> Palette:
    return _DARK if st.context.theme.type == "dark" else _LIGHT


def _action_color(action: str) -> str:
    light, dark = ACTION_COLORS[action]
    return dark if st.context.theme.type == "dark" else light


def stock_projection(proposal: pd.Series, order_qty: int) -> dict[str, Any]:
    """Projected stock for eight weeks, with and without the proposed order."""
    colors = palette()
    days = np.arange(57)
    daily = proposal["weekly_forecast"] / 7
    open_order_day = 5  # Open orders are already in transit
    arrival_day = int(proposal["lead_time_days"])
    without = (
        proposal["on_hand"]
        + np.where(days >= open_order_day, proposal["on_order"], 0)
        - daily * days
    )
    with_order = without + np.where(days >= arrival_day, order_qty, 0)
    dates = pd.date_range(date.today(), periods=len(days), freq="D")
    data = pd.DataFrame(
        {
            "day": dates,
            "Without the order": np.maximum(without, 0).round(),
            "With the order": np.maximum(with_order, 0).round(),
            "Safety stock": round(proposal["weekly_forecast"]),
        }
    )
    stockout = np.flatnonzero(without <= 0)
    marks: list[dict[str, Any]] = [
        {
            "name": "Arrives",
            "xAxis": (date.today() + timedelta(days=arrival_day)).isoformat(),
        }
    ]
    if stockout.size:
        marks.append(
            {
                "name": "Stockout",
                "xAxis": (date.today() + timedelta(days=int(stockout[0]))).isoformat(),
                "lineStyle": {"color": colors.warning},
            }
        )
    return {
        "dataset": {"source": data},
        "legend": {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "%,d units"},
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": {"type": "value"},
        "series": [
            {
                "type": "line",
                "name": "With the order",
                "encode": {"x": "day", "y": "With the order"},
                "showSymbol": False,
                "lineStyle": {"width": 2.5, "color": colors.primary},
                "itemStyle": {"color": colors.primary},
                "areaStyle": {"color": colors.band, "opacity": 0.9},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": colors.text},
                    "label": {"formatter": "{b}", "position": "insideEndTop"},
                    "data": marks,
                },
            },
            {
                "type": "line",
                "name": "Without the order",
                "encode": {"x": "day", "y": "Without the order"},
                "showSymbol": False,
                "lineStyle": {"width": 2, "type": "dashed", "color": colors.warning},
                "itemStyle": {"color": colors.warning},
            },
            {
                "type": "line",
                "name": "Safety stock",
                "encode": {"x": "day", "y": "Safety stock"},
                "showSymbol": False,
                "lineStyle": {"width": 1.5, "type": "dotted", "color": colors.muted},
                "itemStyle": {"color": colors.muted},
            },
        ],
    }


def demand(proposal: pd.Series) -> dict[str, Any]:
    """Twelve weeks of units sold and the agent's six-week forecast."""
    colors = palette()
    history, forecast = proposal["history"], proposal["forecast"]
    start = pd.Timestamp(date.today()) - pd.Timedelta(weeks=len(history))
    weeks = pd.date_range(start, periods=len(history) + len(forecast), freq="7D")
    data = pd.DataFrame(
        {
            "week": [f"{week:%b %-d}" for week in weeks],
            "Sold": [*history] + [None] * len(forecast),
            "Forecast": [None] * (len(history) - 1) + [history[-1], *forecast],
        }
    )
    return {
        "dataset": {"source": data},
        "legend": {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "%,d units"},
        "xAxis": {"type": "category", "axisTick": {"show": False}},
        "yAxis": {"type": "value"},
        "series": [
            {
                "type": "bar",
                "name": "Sold",
                "encode": {"x": "week", "y": "Sold"},
                "itemStyle": {"color": colors.muted},
                "barCategoryGap": "30%",
            },
            {
                "type": "line",
                "name": "Forecast",
                "encode": {"x": "week", "y": "Forecast"},
                "symbolSize": 6,
                "lineStyle": {"width": 2.5, "type": "dashed", "color": colors.primary},
                "itemStyle": {"color": colors.primary},
            },
        ],
    }


def decisions_per_day(decisions: pd.DataFrame) -> dict[str, Any]:
    """Decisions per day, stacked by outcome."""
    counts = (
        decisions.assign(day=decisions["decided_at"].dt.normalize())
        .pivot_table(
            index="day", columns="action", values="proposal_id", aggfunc="count"
        )
        .reindex(columns=list(ACTION_COLORS))
        .fillna(0)
        .reset_index()
    )
    return {
        "dataset": {"source": counts},
        "legend": {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "%d proposals"},
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": {"type": "value"},
        "series": [
            {
                "type": "bar",
                "name": action,
                "stack": "decisions",
                "encode": {"x": "day", "y": action},
                "itemStyle": {"color": _action_color(action)},
                "barMaxWidth": 18,
            }
            for action in ACTION_COLORS
        ],
    }


def acceptance_by_category(decisions: pd.DataFrame) -> dict[str, Any]:
    """Share of each category's proposals approved unchanged."""
    colors = palette()
    shares = (
        decisions.assign(accepted=decisions["action"] == "Approved")
        .groupby("category")["accepted"]
        .mean()
        .sort_values()
        .mul(100)
        .round()
        .reset_index()
    )
    return {
        "dataset": {"source": shares},
        "grid": {"left": 8, "right": 40, "top": 8, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "%.0f%% approved unchanged"},
        "xAxis": {"type": "value", "max": 100, "axisLabel": {"formatter": "{value}%"}},
        "yAxis": {"type": "category", "axisTick": {"show": False}},
        "series": [
            {
                "type": "bar",
                "encode": {"x": "accepted", "y": "category"},
                "itemStyle": {"color": colors.primary},
                "barMaxWidth": 22,
                "label": {
                    "show": True,
                    "position": "right",
                    "formatter": "{@accepted}%",
                },
            }
        ],
    }
