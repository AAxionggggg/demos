"""ECharts options for Cairn Demand lab.

The theme in ``.streamlit/config.toml`` colors the charts: series take the
``chartCategoricalColors`` palette in order, and heatmaps take
``chartSequentialColors``. A few series need a color for their role instead
of their position, such as the forecast bands in the forecast's color or a
neutral "last year" line. They read it from the same theme with ``theme``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import streamlit as st
from utils import model

LEGEND = {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16}


def theme(option: str) -> Any:
    """A color option of the active light or dark theme, such as ``"grayColor"``."""
    mode = "dark" if st.context.theme.type == "dark" else "light"
    return st.get_option(f"theme.{mode}.{option}")


def _millions_axis() -> dict[str, Any]:
    """A value axis for amounts in millions of dollars."""
    return {"type": "value", "axisLabel": {"formatter": "${value}M"}}


def fan_chart(
    history: pd.DataFrame,
    forecast: model.Forecast,
    *,
    metric: str,
    promo: tuple[int, int] | None,
) -> dict[str, Any]:
    """Recent actuals, last year, and the forecast's median with 50% and 80% bands.

    Each band is a translucent area stacked on an invisible line at its lower
    quantile, so the bands never cover the gridlines or the page background.
    """
    forecast_color, supply_color = theme("chartCategoricalColors")[:2]
    weekly = forecast.weekly
    column = "units" if metric == "Units" else "revenue"
    recent = history.tail(26)
    last_year = history.set_index("week")[column].reindex(
        weekly["week"] - pd.Timedelta(weeks=52)
    )
    quantiles = {f"P{q}": weekly[f"{column}_p{q}"] for q in (10, 25, 50, 75, 90)}
    data = pd.concat(
        [
            pd.DataFrame({"week": recent["week"], "Actual": recent[column]}),
            pd.DataFrame(
                {
                    "week": weekly["week"],
                    "Last year": last_year.to_numpy(),
                    **quantiles,
                    "80% range": quantiles["P90"] - quantiles["P10"],
                    "50% range": quantiles["P75"] - quantiles["P25"],
                    "Supply": weekly["supply"] if column == "units" else np.nan,
                }
            ),
        ],
        ignore_index=True,
    )
    # Join the actuals to the forecast so the median line starts at the last week.
    data.loc[len(recent) - 1, "P50"] = recent[column].iloc[-1]

    def line(name: str, y: str, color: str, **style: Any) -> dict[str, Any]:
        return {
            "type": "line",
            "name": name,
            "encode": {"x": "week", "y": y},
            "showSymbol": False,
            "smooth": 0.25,
            "itemStyle": {"color": color},
            "lineStyle": {"color": color, "width": 2, **style},
        }

    def band(name: str, lower: str, opacity: float) -> list[dict[str, Any]]:
        hidden = {"tooltip": {"show": False}, "silent": True, "showSymbol": False}
        return [
            {
                **hidden,
                "type": "line",
                "name": name,
                "stack": name,
                "encode": {"x": "week", "y": lower},
                "smooth": 0.25,
                "lineStyle": {"width": 0},
            },
            {
                **hidden,
                "type": "line",
                "name": name,
                "stack": name,
                "encode": {"x": "week", "y": name},
                "smooth": 0.25,
                "lineStyle": {"width": 0},
                "itemStyle": {"color": forecast_color},
                "areaStyle": {"color": forecast_color, "opacity": opacity},
            },
        ]

    marks: dict[str, Any] = {
        "type": "line",
        "name": "Marks",
        "data": [],
        "markLine": {
            "silent": True,
            "symbol": "none",
            "lineStyle": {"type": "dashed", "color": theme("grayColor")},
            "label": {"formatter": "Today", "position": "insideEndTop"},
            "data": [{"xAxis": model.AS_OF.isoformat()}],
        },
    }
    if promo is not None:
        start, end = promo
        marks["markArea"] = {
            "silent": True,
            "itemStyle": {"color": forecast_color, "opacity": 0.08},
            "label": {"formatter": "Promo", "position": "top"},
            "data": [
                [
                    {"xAxis": weekly["week"].iloc[start].isoformat()},
                    {
                        "xAxis": (
                            weekly["week"].iloc[end] + pd.Timedelta(days=6)
                        ).isoformat()
                    },
                ]
            ],
        }
    median = line("Median forecast", "P50", forecast_color, width=2.5)
    # The tooltip lists the bands' quantiles with the median.
    median["encode"]["tooltip"] = ["P90", "P75", "P50", "P25", "P10"]
    series = [
        line("Actual", "Actual", theme("textColor"), opacity=0.75),
        line("Last year", "Last year", theme("grayColor"), type="dashed", width=1.5),
        *band("80% range", "P10", 0.14),
        *band("50% range", "P25", 0.18),
        median,
    ]
    legend = ["Actual", "Last year", "Median forecast"]
    if column == "units":
        supply = line("Supply", "Supply", supply_color, type="dotted", width=1.5)
        series.append({**supply, "smooth": False, "step": "middle"})
        legend.append("Supply")
    series.append(marks)
    return {
        "dataset": {"source": data},
        "legend": {**LEGEND, "data": legend},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "valueFormatter": "%,d units" if column == "units" else "dollar",
        },
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": {
            "type": "value",
            **({} if column == "units" else {"axisLabel": {"formatter": "${value}"}}),
        },
        "series": series,
    }


def outcome_histogram(outcomes: pd.DataFrame, target: float) -> dict[str, Any]:
    """Distribution of simulated season revenue, split at the revenue target."""
    revenue = outcomes["revenue"].to_numpy()
    counts, edges = np.histogram(revenue, bins=32)
    centers = (edges[:-1] + edges[1:]) / 2
    share = counts / counts.sum()
    labels = [f"${center / 1e6:.2f}M" for center in centers]
    above = centers >= target
    data = pd.DataFrame(
        {
            "revenue": labels,
            "Above target": np.where(above, share, 0),
            "Below target": np.where(above, 0, share),
        }
    )
    target_bin = labels[int(np.clip(np.searchsorted(edges, target) - 1, 0, 31))]
    return {
        "dataset": {"source": data},
        "legend": LEGEND,
        "grid": {"left": 8, "right": 8, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "percent"},
        "xAxis": {"type": "category", "axisLabel": {"interval": 7}},
        "yAxis": {"type": "value", "show": False},
        "series": [
            {
                "type": "bar",
                "stack": "share",
                "barCategoryGap": "8%",
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": theme("textColor")},
                    "label": {"formatter": "{b}", "position": "end"},
                    "data": [
                        {"name": f"Target ${target / 1e6:.2f}M", "xAxis": target_bin}
                    ],
                },
            },
            {
                "type": "bar",
                "stack": "share",
                "barCategoryGap": "8%",
                "itemStyle": {"color": theme("grayColor"), "opacity": 0.5},
            },
        ],
    }


def tornado(sensitivity: pd.DataFrame) -> dict[str, Any]:
    """Change in median season profit when each lever moves down or up."""
    rows = sensitivity.assign(
        spread=(sensitivity["high"] - sensitivity["low"]).abs()
    ).sort_values("spread")

    def bars(column: str, label_column: str) -> list[dict[str, Any] | None]:
        items: list[dict[str, Any] | None] = []
        for _, row in rows.iterrows():
            value = round(float(row[column]))
            # A lever already at its limit can't move further, so it gets no bar.
            if value == 0:
                items.append(None)
                continue
            items.append(
                {
                    "value": value,
                    "label": {
                        "formatter": f"{row[label_column]}  {_signed_money(value)}",
                        "position": "right" if value > 0 else "left",
                    },
                }
            )
        return items

    # A symmetric axis with room on both sides keeps the bar labels inside.
    limit = float(rows[["low", "high"]].abs().to_numpy().max() or 1) * 1.9
    return {
        "legend": LEGEND,
        "grid": {"left": 8, "right": 8, "top": 32, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "dollar"},
        "xAxis": {
            "type": "value",
            "min": -limit,
            "max": limit,
            "axisLabel": {"show": False},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "category",
            "data": rows["lever"].tolist(),
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "series": [
            {
                "type": "bar",
                "name": "Lever down",
                "data": bars("low", "low_label"),
                "barGap": "25%",
                "label": {"show": True, "fontSize": 11},
            },
            {
                "type": "bar",
                "name": "Lever up",
                "data": bars("high", "high_label"),
                "label": {"show": True, "fontSize": 11},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "label": {"show": False},
                    "lineStyle": {"color": theme("grayColor"), "type": "solid"},
                    "data": [{"xAxis": 0}],
                },
            },
        ],
    }


def _signed_money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    value = abs(value)
    if value >= 1e6:
        return f"{sign}${value / 1e6:.2f}M"
    if value >= 1e3:
        return f"{sign}${value / 1e3:.0f}k"
    return f"{sign}${value:.0f}"


def price_curve(curve: pd.DataFrame, current: int) -> dict[str, Any]:
    """Median season profit at each price, with the current and best prices marked."""
    best = curve.loc[curve["profit"].idxmax()]
    now = curve.loc[curve["price_change"] == current].iloc[0]
    data = curve.assign(profit=curve["profit"] / 1e6)[["price", "profit"]]
    return {
        "dataset": {"source": data},
        "grid": {"left": 8, "right": 24, "top": 40, "bottom": 8, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "valueFormatter": "$%.2fM",
            "axisPointer": {"label": {"formatter": "${value}"}},
        },
        "xAxis": {
            "type": "value",
            "min": float(curve["price"].min()),
            "max": float(curve["price"].max()),
            "axisLabel": {
                "formatter": "${value}",
                "showMinLabel": False,
                "showMaxLabel": False,
            },
            "splitLine": {"show": False},
        },
        "yAxis": {**_millions_axis(), "scale": True},
        "series": [
            {
                "type": "line",
                "name": "Median season profit",
                "encode": {"x": "price", "y": "profit", "tooltip": ["profit"]},
                "showSymbol": False,
                "smooth": True,
                "lineStyle": {"width": 2.5},
                "areaStyle": {"opacity": 0.12},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": theme("grayColor")},
                    "label": {"formatter": "{b}", "position": "insideEndTop"},
                    "data": [{"name": "Current", "xAxis": float(now["price"])}],
                },
                "markPoint": {
                    "symbolSize": 44,
                    "label": {"formatter": "Best", "fontSize": 10},
                    "data": [
                        {"coord": [float(best["price"]), float(best["profit"]) / 1e6]}
                    ],
                },
            }
        ],
    }


def profit_surface(
    surface: pd.DataFrame, price_change: int, marketing: float
) -> dict[str, Any]:
    """Heatmap of median season profit over price and marketing spend."""
    best = surface.loc[surface["profit"].idxmax()]
    nearest_price = min(model.SURFACE_PRICES, key=lambda p: abs(p - price_change))
    nearest_spend = min(model.SURFACE_SPEND, key=lambda s: abs(s - marketing))

    def pin(label: str, x: str, y: str) -> dict[str, Any]:
        return {"value": [x, y], "label": {"show": True, "formatter": label}}

    return {
        "dataset": {"source": surface[["price", "marketing", "profit"]]},
        "grid": {"left": 8, "right": 8, "top": 8, "bottom": 56, "containLabel": True},
        "tooltip": {"valueFormatter": "dollar"},
        "xAxis": {
            "type": "category",
            "data": [f"{p:+d}%" for p in model.SURFACE_PRICES],
            "name": "Price vs. list",
            "nameLocation": "middle",
            "nameGap": 28,
            "splitArea": {"show": False},
        },
        "yAxis": {
            "type": "category",
            "data": [f"${s:g}k" for s in model.SURFACE_SPEND],
            "name": "Marketing per week",
            "nameLocation": "middle",
            "nameGap": 52,
        },
        # Without inRange colors, the visualMap uses the theme's sequential palette.
        "visualMap": {
            "type": "continuous",
            # Starting the scale at the lower quartile spends the color range on
            # the region where the choice matters.
            "min": float(surface["profit"].quantile(0.25)),
            "max": float(surface["profit"].max()),
            "calculable": False,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "itemHeight": 220,
            "itemWidth": 10,
            "text": ["More profit", "Less"],
            "dimension": 2,
            "seriesIndex": 0,
        },
        "series": [
            {
                "type": "heatmap",
                "name": "Median season profit",
                "encode": {"x": "price", "y": "marketing", "tooltip": ["profit"]},
                "selectedMode": "single",
                # Gaps between the cells, in the page background color.
                "itemStyle": {
                    "borderColor": theme("backgroundColor"),
                    "borderWidth": 2,
                },
            },
            {
                "type": "scatter",
                "name": "Markers",
                "silent": True,
                "tooltip": {"show": False},
                "symbol": "pin",
                "symbolSize": 40,
                "label": {"fontSize": 10},
                "data": [
                    pin("Now", f"{nearest_price:+d}%", f"${nearest_spend:g}k"),
                    pin("Best", best["price"], best["marketing"]),
                ],
                "z": 5,
            },
        ],
    }


def scenario_boxplot(scenarios: list[tuple[str, np.ndarray]]) -> dict[str, Any]:
    """The spread of season profit across simulations, one box per scenario.

    ``colorBy: "data"`` gives each box its palette color in order, the same
    colors the scenario lines get.
    """
    boxes = [
        [
            round(float(value) / 1e6, 3)
            for value in np.percentile(profit, [5, 25, 50, 75, 95])
        ]
        for _, profit in scenarios
    ]
    return {
        "grid": {"left": 8, "right": 16, "top": 16, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "item", "valueFormatter": "$%.2fM"},
        "xAxis": {"type": "category", "data": [name for name, _ in scenarios]},
        "yAxis": {**_millions_axis(), "scale": True},
        "series": [
            {
                "type": "boxplot",
                "name": "Season profit (P5–P95)",
                "colorBy": "data",
                "data": boxes,
                "boxWidth": [24, 56],
                "itemStyle": {"borderWidth": 2},
            }
        ],
    }


def scenario_lines(weekly: pd.DataFrame) -> dict[str, Any]:
    """Median weekly units sold per scenario. ``weekly`` has one column per scenario."""
    return {
        "dataset": {"source": weekly.reset_index()},
        "legend": {**LEGEND, "type": "scroll"},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "%,d units"},
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": {"type": "value"},
        "series": [
            {
                "type": "line",
                "name": name,
                "encode": {"x": "week", "y": name},
                "showSymbol": False,
                "smooth": 0.25,
                "lineStyle": {"width": 2},
            }
            for name in weekly.columns
        ],
    }
