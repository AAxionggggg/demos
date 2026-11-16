"""ECharts options for Cairn Analyst.

Series take the theme's ``chartCategoricalColors`` in order. Increases and
decreases are statuses, so they use the theme's green and red instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import streamlit as st

from utils import data
from utils.format import money, signed_money

if TYPE_CHECKING:
    from utils.files import Series
    from utils.pricing import Outcome

LEGEND = {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16}
GRID = {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True}


def theme(option: str) -> Any:
    """A color option of the active light or dark theme, such as ``"greenColor"``."""
    mode = "dark" if st.context.theme.type == "dark" else "light"
    return st.get_option(f"theme.{mode}.{option}")


def revenue_bridge(change: data.RevenueChange) -> dict[str, Any]:
    """A waterfall from the week before to last week, one bar per driver."""
    # Two-line labels, so every step fits under its bar.
    rows = [("Week\nbefore", 0.0, change.previous_revenue, None, None)]
    level = change.previous_revenue
    for driver in change.drivers:
        low = min(level, level + driver.change)
        up, down = (
            (driver.change, None) if driver.change >= 0 else (None, -driver.change)
        )
        rows.append((driver.label.replace(" ", "\n", 1), low, None, up, down))
        level += driver.change
    rows.append(("Last\nweek", 0.0, change.revenue, None, None))

    frame = pd.DataFrame(
        rows, columns=["step", "base", "total", "increase", "decrease"]
    )
    for column in ("base", "total", "increase", "decrease"):
        frame[column] = frame[column] / 1_000
    labels = [money(change.previous_revenue)]
    labels += [signed_money(d.change) for d in change.drivers]
    labels += [money(change.revenue)]
    frame["label"] = labels

    floor = min(change.revenue, change.previous_revenue) * 0.9 / 1_000
    label = {"show": True, "position": "top", "formatter": "{@label}"}
    tooltip = {"formatter": "{b}: {@label}"}

    def bars(name: str, color: str) -> dict[str, Any]:
        return {
            "type": "bar",
            "name": name,
            "stack": "bridge",
            "encode": {"x": "step", "y": name.lower()},
            "itemStyle": {"color": theme(color)},
            "label": label,
            "tooltip": tooltip,
            "barWidth": "56%",
        }

    return {
        "dataset": {"source": frame},
        "grid": {**GRID, "top": 24},
        "tooltip": {"trigger": "item"},
        "xAxis": {
            "type": "category",
            "axisTick": {"show": False},
            "axisLabel": {"interval": 0, "lineHeight": 15},
        },
        "yAxis": {
            "type": "value",
            "min": round(floor, -1),
            "axisLabel": {"formatter": "${value}k"},
        },
        "series": [
            {
                "type": "bar",
                "name": "base",
                "stack": "bridge",
                "encode": {"x": "step", "y": "base"},
                "itemStyle": {"color": "transparent"},
                "emphasis": {"disabled": True},
                "tooltip": {"show": False},
                "silent": True,
            },
            bars("Total", "grayColor"),
            bars("Increase", "greenColor"),
            bars("Decrease", "redColor"),
        ],
    }


def revenue_trend(change: data.RevenueChange) -> dict[str, Any]:
    """Weekly net revenue per channel, in thousands."""
    frame = change.trend.copy()
    frame["week"] = frame["week"].map(data.week_label)
    for channel in data.CHANNELS:
        frame[channel] = (frame[channel] / 1_000).round()
    return {
        "dataset": {"source": frame},
        "legend": LEGEND,
        "grid": GRID,
        "tooltip": {"trigger": "axis", "valueFormatter": "$%,dk"},
        "xAxis": {"type": "category", "boundaryGap": False},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}k"}},
        "series": [
            {"type": "line", "name": channel, "showSymbol": False, "smooth": 0.2}
            for channel in data.CHANNELS
        ],
    }


def margin_range(outcomes: list[Outcome]) -> dict[str, Any]:
    """Gross margin per price: the middle 50% of futures as a box, 5–95% as whiskers."""
    names = [
        f"${o.price:.0f} ({'current' if o.label == 'Current price' else o.label})"
        for o in outcomes
    ]
    boxes = [
        [round(float(np.percentile(o.margin, q)) / 1_000) for q in (5, 25, 50, 75, 95)]
        for o in outcomes
    ]
    return {
        "grid": {**GRID, "top": 16},
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "category", "data": names, "axisTick": {"show": False}},
        "yAxis": {
            "type": "value",
            "scale": True,
            "axisLabel": {"formatter": "${value}k"},
        },
        "series": [
            {
                "type": "boxplot",
                "name": "Gross margin, next 8 weeks",
                "data": boxes,
                "boxWidth": [28, 56],
                "itemStyle": {
                    "color": theme("secondaryBackgroundColor"),
                    "borderColor": theme("primaryColor"),
                    "borderWidth": 1.5,
                },
            }
        ],
    }


def weekly_units(outcomes: list[Outcome]) -> dict[str, Any]:
    """Median units sold per week at each price, against the supply."""
    frame = pd.DataFrame(
        {"week": [f"Week {i + 1}" for i in range(len(data.JACKET_SUPPLY))]}
    )
    for outcome in outcomes:
        frame[f"${outcome.price:.0f}"] = np.median(outcome.units, axis=0).round()
    frame["Supply"] = data.JACKET_SUPPLY
    prices = [f"${o.price:.0f}" for o in outcomes]
    return {
        "dataset": {"source": frame},
        "legend": {**LEGEND, "data": [*prices, "Supply"]},
        "grid": GRID,
        "tooltip": {"trigger": "axis", "valueFormatter": "%,d units"},
        "xAxis": {"type": "category", "boundaryGap": False},
        "yAxis": {"type": "value"},
        "series": [
            *({"type": "line", "name": p, "showSymbol": False} for p in prices),
            {
                "type": "line",
                "name": "Supply",
                "step": "end",
                "showSymbol": False,
                "lineStyle": {
                    "type": "dashed",
                    "width": 1.5,
                    "color": theme("grayColor"),
                },
                "itemStyle": {"color": theme("grayColor")},
            },
        ],
    }


def file_series(series: Series) -> dict[str, Any]:
    """The time series found in an attached file."""
    return {
        "dataset": {"source": series.frame},
        "grid": {**GRID, "top": 16},
        "tooltip": {"trigger": "axis", "valueFormatter": "%,.4g"},
        "xAxis": {"type": "time"},
        "yAxis": {"type": "value", "scale": True},
        "series": [
            {
                "type": "line",
                "name": series.value,
                "showSymbol": series.points <= 40,
                "areaStyle": {"opacity": 0.12},
                "encode": {"x": series.date, "y": series.value},
            }
        ],
    }
