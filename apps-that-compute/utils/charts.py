"""ECharts options for Cairn Demand lab.

Series colors come from the theme's categorical palette in
``.streamlit/config.toml``. Charts that need a specific color for a role (the
forecast bands, the supply line) pick it for the active light or dark theme.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

import streamlit as st
from utils import model


@dataclass(frozen=True)
class Palette:
    series: tuple[str, ...]
    forecast: str
    band_outer: str
    band_inner: str
    background: str
    actual: str
    last_year: str
    supply: str
    highlight: str  # Tints a marked range, such as the promo weeks
    highlight_opacity: float
    gain: str
    loss: str
    sequential: tuple[str, ...]


# The bands are the forecast color blended into the page background, and
# ``background`` must match the theme's backgroundColor.
_LIGHT = Palette(
    series=("#C2410C", "#008A7B", "#5B5BD6", "#B7791F", "#BE185D", "#0369A1"),
    forecast="#C2410C",
    band_outer="#F3DFD4",
    band_inner="#EAC2AE",
    background="#FBF9F4",
    actual="#4A4036",
    last_year="#B1A799",
    supply="#008A7B",
    highlight="#1F1A14",
    highlight_opacity=0.05,
    gain="#008A7B",
    loss="#C2410C",
    sequential=("#FBEEE4", "#F0C2A1", "#DC8350", "#C2410C", "#802A07"),
)
_DARK = Palette(
    series=("#E0703A", "#1E9E93", "#7B76EE", "#C08A1C", "#E0558F", "#3A9BDA"),
    forecast="#E0703A",
    band_outer="#352216",
    band_inner="#56311D",
    background="#15130F",
    actual="#D6CDBF",
    last_year="#6B6258",
    supply="#1E9E93",
    highlight="#FFFFFF",
    highlight_opacity=0.05,
    gain="#1E9E93",
    loss="#E0703A",
    sequential=("#2A1A12", "#4C2716", "#91441F", "#C9663A", "#F2B48F"),
)


def palette() -> Palette:
    return _DARK if st.context.theme.type == "dark" else _LIGHT


def _millions_axis() -> dict[str, Any]:
    """A value axis for amounts in millions of dollars."""
    return {"type": "value", "axisLabel": {"formatter": "${value}M"}}


def _marker_label(text: str, colors: Palette) -> dict[str, Any]:
    return {
        "show": True,
        "formatter": text,
        "position": "top",
        "distance": 6,
        "fontSize": 11,
        "fontWeight": 600,
        "color": colors.actual,
        "backgroundColor": colors.background,
        "padding": [2, 6],
        "borderRadius": 4,
    }


def fan_chart(
    history: pd.DataFrame,
    forecast: model.Forecast,
    *,
    metric: str,
    promo: tuple[int, int] | None,
) -> dict[str, Any]:
    """Recent actuals, last year, and the forecast's median with 50% and 80% bands.

    The bands are opaque areas drawn from the top quantile down, each one
    painting over the area below it, so the tooltip lists the real quantiles.
    """
    colors = palette()
    weekly = forecast.weekly
    column = "units" if metric == "Units" else "revenue"
    recent = history.tail(26)
    last_year = history.set_index("week")[column].reindex(
        weekly["week"] - pd.Timedelta(weeks=52)
    )
    data = pd.concat(
        [
            pd.DataFrame({"week": recent["week"], "Actual": recent[column]}),
            pd.DataFrame(
                {
                    "week": weekly["week"],
                    "Last year": last_year.to_numpy(),
                    "P90": weekly[f"{column}_p90"],
                    "P75": weekly[f"{column}_p75"],
                    "Median forecast": weekly[f"{column}_p50"],
                    "P25": weekly[f"{column}_p25"],
                    "P10": weekly[f"{column}_p10"],
                    "Supply": weekly["supply"] if column == "units" else np.nan,
                }
            ),
        ],
        ignore_index=True,
    )
    # Join the actuals to the forecast so the median line starts at the last week.
    data.loc[len(recent) - 1, "Median forecast"] = recent[column].iloc[-1]

    def band(name: str, color: str, z: int) -> dict[str, Any]:
        return {
            "type": "line",
            "name": name,
            "encode": {"x": "week", "y": name},
            "showSymbol": False,
            "lineStyle": {"width": 0},
            "areaStyle": {"color": color, "opacity": 1},
            "itemStyle": {"color": color},
            "smooth": 0.25,
            "z": z,
        }

    def line(name: str, color: str, z: int, **style: Any) -> dict[str, Any]:
        return {
            "type": "line",
            "name": name,
            "encode": {"x": "week", "y": name},
            "showSymbol": False,
            "itemStyle": {"color": color},
            "lineStyle": {"color": color, "width": 2, **style},
            "smooth": 0.25,
            "z": z,
        }

    marks: dict[str, Any] = {
        "type": "line",
        "name": "Marks",
        "data": [],
        "itemStyle": {"color": colors.actual},
        "markLine": {
            "silent": True,
            "symbol": "none",
            "lineStyle": {"type": "dashed", "color": colors.last_year},
            "label": {"formatter": "Today", "position": "insideEndTop"},
            "data": [{"xAxis": model.AS_OF.isoformat()}],
        },
        "z": 9,
    }
    if promo is not None:
        start, end = promo
        marks["markArea"] = {
            "silent": True,
            "itemStyle": {
                "color": colors.highlight,
                "opacity": colors.highlight_opacity,
            },
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
    series = [
        line("Actual", colors.actual, 6),
        line("Last year", colors.last_year, 5, type="dashed", width=1.5),
        band("P90", colors.band_outer, 1),
        band("P75", colors.band_inner, 2),
        line("Median forecast", colors.forecast, 7, width=2.5),
        band("P25", colors.band_outer, 3),
        band("P10", colors.background, 4),
    ]
    legend = ["Actual", "Last year", "Median forecast"]
    if column == "units":
        series.append(
            {
                **line("Supply", colors.supply, 8, type="dotted", width=1.5),
                "smooth": False,
                "step": "middle",
            }
        )
        legend.append("Supply")
    series.append(marks)
    return {
        "dataset": {"source": data},
        "legend": {"data": legend, "top": 0, "right": 6, "icon": "roundRect", "itemGap": 16},
        "grid": {"left": 8, "right": 16, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "valueFormatter": "%,d units" if column == "units" else "dollar",
        },
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": {
            "type": "value",
            "splitLine": {"show": False},
            **({} if column == "units" else {"axisLabel": {"formatter": "${value}"}}),
        },
        "series": series,
    }


def outcome_histogram(outcomes: pd.DataFrame, target: float) -> dict[str, Any]:
    """Distribution of simulated season revenue, split at the revenue target."""
    colors = palette()
    revenue = outcomes["revenue"].to_numpy()
    counts, edges = np.histogram(revenue, bins=32)
    centers = (edges[:-1] + edges[1:]) / 2
    share = counts / counts.sum()
    labels = [f"${center / 1e6:.2f}M" for center in centers]
    above = centers >= target
    data = pd.DataFrame(
        {
            "revenue": labels,
            "Below target": np.where(above, 0, share),
            "Above target": np.where(above, share, 0),
        }
    )
    target_bin = labels[int(np.clip(np.searchsorted(edges, target) - 1, 0, 31))]
    return {
        "dataset": {"source": data},
        "legend": {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16},
        "grid": {"left": 8, "right": 8, "top": 36, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "valueFormatter": "percent"},
        "xAxis": {"type": "category", "axisLabel": {"interval": 7}},
        "yAxis": {"type": "value", "show": False},
        "series": [
            {
                "type": "bar",
                "stack": "share",
                "itemStyle": {"color": colors.last_year},
                "barCategoryGap": "8%",
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": colors.actual},
                    "label": {"formatter": "{b}", "position": "end"},
                    "data": [
                        {"name": f"Target ${target / 1e6:.2f}M", "xAxis": target_bin}
                    ],
                },
            },
            {
                "type": "bar",
                "stack": "share",
                "itemStyle": {"color": colors.forecast},
                "barCategoryGap": "8%",
            },
        ],
    }


def tornado(sensitivity: pd.DataFrame) -> dict[str, Any]:
    """Change in median season profit when each lever moves down or up."""
    colors = palette()
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
                    "itemStyle": {"color": colors.gain if value > 0 else colors.loss},
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
        "grid": {"left": 8, "right": 8, "top": 8, "bottom": 8, "containLabel": True},
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
                "itemStyle": {"borderRadius": 4},
            },
            {
                "type": "bar",
                "name": "Lever up",
                "data": bars("high", "high_label"),
                "label": {"show": True, "fontSize": 11},
                "itemStyle": {"borderRadius": 4},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "label": {"show": False},
                    "lineStyle": {"color": colors.last_year, "type": "solid"},
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
    colors = palette()
    best = curve.loc[curve["profit"].idxmax()]
    now = curve.loc[curve["price_change"] == current].iloc[0]
    data = curve.assign(profit=curve["profit"] / 1e6)[["price", "profit"]]
    return {
        "dataset": {"source": data},
        "grid": {"left": 8, "right": 24, "top": 24, "bottom": 8, "containLabel": True},
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
                "lineStyle": {"width": 2.5, "color": colors.forecast},
                "itemStyle": {"color": colors.forecast},
                "areaStyle": {"color": colors.band_outer, "opacity": 0.8},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": colors.actual},
                    "label": {"formatter": "{b}", "position": "insideEndTop"},
                    "data": [{"name": "Current", "xAxis": float(now["price"])}],
                },
                "markPoint": {
                    "symbol": "circle",
                    "symbolSize": 12,
                    "itemStyle": {
                        "color": colors.supply,
                        "borderColor": colors.background,
                        "borderWidth": 2,
                    },
                    "label": {
                        "formatter": f"Best ${best['price']:.0f}",
                        "position": "top",
                        "distance": 8,
                    },
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
    colors = palette()
    best = surface.loc[surface["profit"].idxmax()]
    nearest_price = min(model.SURFACE_PRICES, key=lambda p: abs(p - price_change))
    nearest_spend = min(model.SURFACE_SPEND, key=lambda s: abs(s - marketing))
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
            "inRange": {"color": list(colors.sequential)},
            "dimension": 2,
            "seriesIndex": 0,
        },
        "series": [
            {
                "type": "heatmap",
                "name": "Median season profit",
                "encode": {"x": "price", "y": "marketing", "tooltip": ["profit"]},
                "selectedMode": "single",
                "itemStyle": {"borderColor": colors.background, "borderWidth": 2},
                "emphasis": {"itemStyle": {"borderColor": colors.actual}},
                "select": {
                    "itemStyle": {"borderColor": colors.supply, "borderWidth": 2}
                },
            },
            {
                "type": "scatter",
                "name": "Markers",
                "silent": True,
                "tooltip": {"show": False},
                "data": [
                    {
                        "value": [f"{nearest_price:+d}%", f"${nearest_spend:g}k"],
                        "symbol": "circle",
                        "symbolSize": 12,
                        "itemStyle": {
                            "color": colors.background,
                            "borderColor": colors.actual,
                            "borderWidth": 3,
                        },
                        "label": _marker_label("Now", colors),
                    },
                    {
                        "value": [best["price"], best["marketing"]],
                        "symbol": "circle",
                        "symbolSize": 12,
                        "itemStyle": {
                            "color": colors.supply,
                            "borderColor": colors.background,
                            "borderWidth": 2,
                        },
                        "label": _marker_label("Best", colors),
                    },
                ],
                "z": 5,
            },
        ],
    }


def scenario_boxplot(scenarios: list[tuple[str, np.ndarray]]) -> dict[str, Any]:
    """The spread of season profit across simulations, one box per scenario."""
    colors = palette()
    boxes = []
    for index, (_, profit) in enumerate(scenarios):
        p5, p25, p50, p75, p95 = np.percentile(profit, [5, 25, 50, 75, 95])
        color = colors.series[index % len(colors.series)]
        boxes.append(
            {
                "value": [round(float(v) / 1e6, 3) for v in (p5, p25, p50, p75, p95)],
                "itemStyle": {"color": colors.background, "borderColor": color},
            }
        )
    return {
        "grid": {"left": 8, "right": 16, "top": 16, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "item", "valueFormatter": "$%.2fM"},
        "xAxis": {"type": "category", "data": [name for name, _ in scenarios]},
        "yAxis": {**_millions_axis(), "scale": True},
        "series": [
            {
                "type": "boxplot",
                "name": "Season profit (P5–P95)",
                "data": boxes,
                "boxWidth": [24, 56],
                "itemStyle": {"borderWidth": 2},
            }
        ],
    }


def scenario_lines(weekly: pd.DataFrame) -> dict[str, Any]:
    """Median weekly units sold per scenario. ``weekly`` has one column per scenario."""
    colors = palette()
    return {
        "dataset": {"source": weekly.reset_index()},
        "color": list(colors.series),
        "legend": {"top": 0, "right": 6, "icon": "roundRect", "itemGap": 16, "type": "scroll"},
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
