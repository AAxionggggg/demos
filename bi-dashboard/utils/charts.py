"""Apache ECharts option builders for the Nimbus BI demo.

Every option leaves series colors to Streamlit's ECharts theme, which reads
``chartCategoricalColors`` / ``chartSequentialColors`` from
``.streamlit/config.toml``. Series always keep a fixed order, so a filter that
removes a category hides its data instead of repainting the survivors.

Charts read their data from a dataframe in ``dataset.source``, which Streamlit
sends as Arrow and shows under **Show data** in the chart toolbar. A few keep
inline ``series.data``: sankeys and gauges don't read datasets, the radar
styles each of its two items differently, and the scatter sizes each bubble by
seats. A dataset could only size bubbles through a ``visualMap``, and
Streamlit's theme gives every ``visualMap`` the sequential palette, which
would recolor the bubbles by size instead of by plan.

Time-series charts draw milestone annotations and the forecast range on an
extra, empty "Markers" series, so the dataset stays the chart's real data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from utils.data import PLANS, PRODUCTS, SOURCES, STAGES
from utils.formatting import money

_LEGEND_TOP = {
    "top": 0,
    "left": 0,
    "icon": "roundRect",
    "itemWidth": 10,
    "itemHeight": 10,
}
_GRID = {"left": 4, "right": 12, "top": 36, "bottom": 4}
_AXIS_TOOLTIP = {"trigger": "axis", "axisPointer": {"type": "line"}}
# Annotation color: a neutral gray that reads on both the light and dark theme.
_MARKER_GRAY = "#8E90A2"
# Diagonal white stripes that mark projected (not yet booked) values.
_HATCH = {
    "color": "rgba(255, 255, 255, 0.55)",
    "dashArrayX": [1, 0],
    "dashArrayY": [3, 4],
    "rotation": -0.785,
}


def _month_labels(index: pd.Index) -> pd.Index:
    return pd.DatetimeIndex(index).strftime("%b %y")


def _markers(
    milestones: list[tuple[pd.Timestamp, str]],
    forecast: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """An empty series that draws milestone lines and a shaded forecast range.

    It has an explicit color, so it doesn't take a palette slot from the data series.
    """
    series: dict[str, Any] = {
        "name": "Markers",
        "type": "line",
        "data": [],
        "silent": True,
        "itemStyle": {"color": _MARKER_GRAY},
        "tooltip": {"show": False},
    }
    if milestones:
        labels = _month_labels(pd.DatetimeIndex([month for month, _ in milestones]))
        series["markLine"] = {
            "silent": True,
            "symbol": ["none", "none"],
            "lineStyle": {"color": _MARKER_GRAY, "type": "dashed", "opacity": 0.8},
            "label": {
                "color": _MARKER_GRAY,
                "position": "insideEndTop",
                "fontSize": 11,
                "formatter": "{b}",
            },
            "data": [
                {"name": text, "xAxis": label}
                for label, (_, text) in zip(labels, milestones, strict=True)
            ],
        }
    if forecast:
        series["markArea"] = {
            "silent": True,
            "itemStyle": {"color": "rgba(142, 144, 162, 0.14)"},
            "label": {"color": _MARKER_GRAY, "position": "insideTop", "fontSize": 11},
            "data": [
                [{"name": "Forecast", "xAxis": forecast[0]}, {"xAxis": forecast[1]}]
            ],
        }
    return series


def mrr_growth(
    monthly: pd.DataFrame,
    active_plans: tuple[str, ...],
    *,
    share: bool,
    forecast: pd.DataFrame | None = None,
    year_earlier: pd.DataFrame | None = None,
    milestones: list[tuple[pd.Timestamp, str]] | None = None,
) -> dict[str, Any]:
    """Stacked area of MRR (in $K, or % share) per plan over time.

    ``forecast`` appends projected months under a shaded range, and
    ``year_earlier`` adds the total MRR of the same months a year before as a
    dashed line (in $K only).
    """
    combined = monthly if forecast is None else pd.concat([monthly, forecast])
    values = combined[list(active_plans)] if active_plans else combined.iloc[:, :0]
    if share:
        values = values.div(values.sum(axis=1).replace(0, 1), axis=0) * 100
    else:
        values = values / 1_000
    # A plan removed by the global filter keeps its column (and color slot)
    # but has no values, so it draws nothing.
    source = values.reindex(columns=PLANS).round(1).reset_index(drop=True)
    labels = _month_labels(combined.index)
    source.insert(0, "month", labels)
    series = [
        {
            "name": plan,
            "type": "line",
            "stack": "mrr",
            "smooth": 0.35,
            "showSymbol": False,
            "lineStyle": {"width": 2},
            "areaStyle": {"opacity": 0.22},
            "emphasis": {"focus": "series"},
            "encode": {"x": "month", "y": plan},
        }
        for plan in PLANS
    ]
    legend = list(PLANS)
    if year_earlier is not None and not share:
        total = year_earlier[list(active_plans)].sum(axis=1) / 1_000
        # Forecast months have no year-earlier value, so they stay empty.
        source["Year earlier"] = total.reindex(combined.index).round(1).to_numpy()
        series.append(
            {
                "name": "Year earlier",
                "type": "line",
                "smooth": 0.35,
                "showSymbol": False,
                "lineStyle": {"width": 2, "type": "dashed"},
                "encode": {"x": "month", "y": "Year earlier"},
            }
        )
        legend.append("Year earlier")
    forecast_range = (
        (labels[len(monthly)], labels[-1]) if forecast is not None else None
    )
    series.append(_markers(milestones or [], forecast_range))
    return {
        "dataset": {"source": source},
        "tooltip": {
            **_AXIS_TOOLTIP,
            "valueFormatter": "%.1f%%" if share else "$%,.1fK",
        },
        "legend": {**_LEGEND_TOP, "data": legend},
        "grid": _GRID,
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "max": 100 if share else None,
            "axisLabel": {"formatter": "{value}%" if share else "${value}K"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "series": series,
    }


def bookings(
    monthly: pd.DataFrame, milestones: list[tuple[pd.Timestamp, str]] | None = None
) -> dict[str, Any]:
    """Stacked bars of closed-won bookings in $K, with the current month's projection hatched."""
    source = (
        (monthly / 1_000)
        .round(1)
        .rename(columns={"won": "Closed won", "projected": "Projected"})
        .reset_index(drop=True)
    )
    # Only the current month has a projection; empty values draw no bar.
    source["Projected"] = source["Projected"].where(source["Projected"] > 0)
    source.insert(0, "month", _month_labels(monthly.index))
    bar = {"type": "bar", "stack": "bookings", "barWidth": "62%"}
    return {
        "dataset": {"source": source},
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "valueFormatter": "$%,.0fK",
        },
        "legend": {**_LEGEND_TOP, "data": ["Closed won", "Projected"]},
        "grid": _GRID,
        "xAxis": {"type": "category", "axisTick": {"show": False}},
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "${value}K"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "series": [
            {**bar, "name": "Closed won", "encode": {"x": "month", "y": "Closed won"}},
            {
                **bar,
                "name": "Projected",
                "itemStyle": {"opacity": 0.7, "decal": _HATCH},
                "encode": {"x": "month", "y": "Projected"},
            },
            _markers(milestones or []),
        ],
    }


def mrr_bridge(movements: dict[str, float]) -> dict[str, Any]:
    """Waterfall from starting to ending MRR, in $K."""
    steps = [
        ("Start", movements["start"], "total"),
        ("New", movements["new"], "increase"),
        ("Expand", movements["expansion"], "increase"),
        ("Contract", -movements["contraction"], "decrease"),
        ("Churn", -movements["churn"], "decrease"),
        ("End", movements["end"], "total"),
    ]
    rows = []
    level = 0.0
    for name, value, kind in steps:
        if kind == "total":
            level = value
            base = 0.0
        elif kind == "increase":
            base = level
            level += value
        else:
            level += value
            base = level
        height = round(abs(value) / 1_000, 1)
        rows.append(
            {
                "step": name,
                "Base": round(base / 1_000, 1),
                # Each step fills only the column of its own kind.
                "MRR": height if kind == "total" else None,
                "Gain": height if kind == "increase" else None,
                "Loss": height if kind == "decrease" else None,
                # Precomputed because labels can't apply a number format.
                "change": money(value),
            }
        )

    bar_style = {
        "type": "bar",
        "stack": "bridge",
        "barWidth": "56%",
        "itemStyle": {"borderRadius": 4},
    }
    label = {
        "show": True,
        "position": "top",
        "fontWeight": 500,
        "formatter": "{@change}",
    }
    return {
        "dataset": {"source": pd.DataFrame(rows)},
        "tooltip": {"trigger": "item"},
        "legend": {**_LEGEND_TOP, "data": ["MRR", "Gain", "Loss"]},
        "grid": {**_GRID, "top": 44},
        "xAxis": {
            "type": "category",
            "axisTick": {"show": False},
            "axisLabel": {"interval": 0},
        },
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}K"}},
        "series": [
            {
                # Transparent spacer that lifts the floating bars. A series
                # with an explicit color doesn't consume a palette slot.
                **bar_style,
                "name": "Base",
                "itemStyle": {"color": "transparent"},
                "emphasis": {"disabled": True},
                "tooltip": {"show": False},
                "silent": True,
                "encode": {"x": "step", "y": "Base"},
            },
            *(
                {
                    **bar_style,
                    "name": name,
                    "label": label,
                    "tooltip": {"formatter": "{b}: {@change}"},
                    "encode": {"x": "step", "y": name},
                }
                for name in ("MRR", "Gain", "Loss")
            ),
        ],
    }


def industry_mix(mrr_by_industry: pd.Series) -> dict[str, Any]:
    """Selectable donut of MRR by industry, with the total in the center."""
    total_k = mrr_by_industry.sum() / 1_000
    total_label = (
        f"${total_k / 1_000:.2f}M" if total_k >= 1_000 else f"${total_k:,.0f}K"
    )
    source = (
        (mrr_by_industry / 1_000)
        .round(1)
        .rename("mrr")
        .rename_axis("industry")
        .reset_index()
    )
    return {
        "dataset": {"source": source},
        # Pie tooltips leave named {@...} placeholders empty, so read the MRR
        # column by position.
        "tooltip": {"trigger": "item", "formatter": "{b}: ${@[1]}K ({d}%)"},
        "legend": {"bottom": 0, "icon": "circle", "itemWidth": 8, "itemHeight": 8},
        "title": {
            "text": total_label,
            "subtext": "MRR",
            "left": "center",
            "top": "34%",
            "textStyle": {"fontSize": 22, "fontWeight": 600},
        },
        "series": [
            {
                "name": "Industry",
                "type": "pie",
                "radius": ["58%", "80%"],
                "center": ["50%", "42%"],
                "padAngle": 2,
                "itemStyle": {"borderRadius": 6},
                "label": {"show": False},
                "selectedMode": "single",
                "selectedOffset": 8,
                "emphasis": {"scale": True, "scaleSize": 4},
                "encode": {"itemName": "industry", "value": "mrr"},
            }
        ],
    }


def usage_heatmap(matrix: pd.DataFrame) -> dict[str, Any]:
    """Weekday by hour heatmap of product sessions."""
    # Category axes read numbers as positions, so the hours become labels.
    source = (
        matrix.set_axis([f"{hour:02d}:00" for hour in matrix.columns], axis=1)
        .rename_axis("weekday")
        .reset_index()
        .melt(id_vars="weekday", var_name="hour", value_name="sessions")
    )[["hour", "weekday", "sessions"]]
    return {
        "dataset": {"source": source},
        "tooltip": {"position": "top"},
        "grid": {"left": 4, "right": 4, "top": 8, "bottom": 48},
        "xAxis": {
            "type": "category",
            "splitArea": {"show": False},
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "yAxis": {
            "type": "category",
            "inverse": True,
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "visualMap": {
            "dimension": "sessions",
            "min": 0,
            "max": int(matrix.to_numpy().max()) or 1,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "itemHeight": 220,
            "itemWidth": 10,
            "calculable": False,
            "text": ["More", "Fewer"],
        },
        "series": [
            {
                "name": "Sessions",
                "type": "heatmap",
                "encode": {"x": "hour", "y": "weekday", "value": "sessions"},
                "tooltip": {
                    "formatter": "{@weekday} {@hour} UTC · {@sessions} sessions"
                },
                "itemStyle": {"borderRadius": 3},
                "emphasis": {
                    "itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(0, 0, 0, 0.25)"}
                },
            }
        ],
    }


def account_mrr(history: pd.Series) -> dict[str, Any]:
    """Single-series MRR history for the account drawer."""
    active = history[history > 0]
    if active.empty:
        active = history.tail(12)
    source = active.round().rename("mrr").reset_index(drop=True).to_frame()
    source.insert(0, "month", _month_labels(active.index))
    return {
        "dataset": {"source": source},
        "tooltip": {**_AXIS_TOOLTIP, "valueFormatter": "$%,d"},
        "grid": {"left": 4, "right": 8, "top": 12, "bottom": 4},
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "${value}"},
            "scale": True,
        },
        "series": [
            {
                "name": "MRR",
                "type": "line",
                "smooth": 0.3,
                "showSymbol": False,
                "lineStyle": {"width": 2.5},
                "areaStyle": {"opacity": 0.16},
                "encode": {"x": "month", "y": "mrr"},
            }
        ],
    }


def product_adoption(account: list[int], plan_average: list[float]) -> dict[str, Any]:
    """Radar of product adoption for one account against its plan average."""
    return {
        "tooltip": {},
        "legend": {"bottom": 0, "icon": "roundRect", "itemWidth": 10, "itemHeight": 10},
        "radar": {
            "indicator": [{"name": product, "max": 100} for product in PRODUCTS],
            "radius": "66%",
            "center": ["50%", "46%"],
            "splitNumber": 4,
        },
        "series": [
            {
                "type": "radar",
                "symbolSize": 6,
                "data": [
                    {
                        "name": "This account",
                        "value": account,
                        "areaStyle": {"opacity": 0.28},
                        "lineStyle": {"width": 2},
                    },
                    {
                        "name": "Plan average",
                        "value": [round(v) for v in plan_average],
                        "areaStyle": {"opacity": 0.08},
                        "lineStyle": {"width": 1.5, "type": "dashed"},
                    },
                ],
            }
        ],
    }


def health_scatter(accounts: pd.DataFrame) -> dict[str, Any]:
    """Health score against MRR, one series per plan, with brush selection."""
    series = []
    for plan in PLANS:
        subset = accounts[accounts["plan"] == plan]
        series.append(
            {
                "name": plan,
                "type": "scatter",
                "data": [
                    {
                        "name": name,
                        "value": [int(health), float(mrr), int(seats)],
                        "symbolSize": max(8, min(28, 6 + seats**0.5)),
                        "tooltip": {
                            "formatter": f"{name} · Health {int(health)} · {money(mrr)} MRR"
                        },
                    }
                    for name, health, mrr, seats in zip(
                        subset["name"],
                        subset["health"],
                        subset["mrr"],
                        subset["seats"],
                        strict=True,
                    )
                ],
                "itemStyle": {"opacity": 0.75},
                "emphasis": {"focus": "series"},
            }
        )
    return {
        "tooltip": {"trigger": "item"},
        # Streamlit's hover toolbar sits in the top-right corner, so the
        # brush tools go top-left with the legend after them.
        "legend": {**_LEGEND_TOP, "left": 64},
        "grid": {**_GRID, "top": 40, "right": 40},
        "toolbox": {
            "left": 0,
            "top": 0,
            "feature": {
                "brush": {
                    "type": ["rect", "clear"],
                    "title": {"rect": "Select", "clear": "Clear"},
                }
            },
        },
        "brush": {
            "xAxisIndex": 0,
            "yAxisIndex": 0,
            "throttleType": "debounce",
            "throttleDelay": 300,
        },
        "xAxis": {
            "type": "value",
            "name": "Health score",
            "nameLocation": "middle",
            "nameGap": 28,
            "min": 0,
            "max": 100,
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "log",
            "min": 100,
            "max": max(1_000, float(accounts["mrr"].max()) * 1.5)
            if len(accounts)
            else 1_000,
            "axisLabel": {"formatter": "${value}"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "series": series,
    }


def stage_funnel(deals: pd.DataFrame) -> dict[str, Any]:
    """Funnel of how many deals reached each stage, in a single hue."""
    order = STAGES[:5]
    ranks = deals["stage"].map(_stage_rank)
    source = pd.DataFrame(
        {"stage": order, "deals": [(ranks >= rank).sum() for rank in range(len(order))]}
    )
    return {
        "dataset": {"source": source},
        # Funnel tooltips leave named {@...} placeholders empty, so read the
        # deals column by position.
        "tooltip": {"trigger": "item", "formatter": "{b}: {@[1]} deals"},
        "series": [
            {
                "name": "Deals",
                "type": "funnel",
                "left": "4%",
                "width": "92%",
                "top": 8,
                "bottom": 8,
                "sort": "none",
                "gap": 3,
                "minSize": "30%",
                # Every stage uses the first palette slot; the shape already
                # encodes the order. The theme's primary color is dark enough
                # for white text in both modes, like a primary button label.
                "colorBy": "series",
                "label": {
                    "show": True,
                    "position": "inside",
                    "formatter": "{b}  ·  {@deals}",
                    "color": "#FFFFFF",
                    "textBorderWidth": 0,
                    "fontWeight": 500,
                },
                "itemStyle": {"borderWidth": 0, "borderRadius": 6},
                "encode": {"itemName": "stage", "value": "deals"},
            }
        ],
    }


def _stage_rank(stage: str) -> int:
    # Closed lost deals made it past discovery on average, so count them as
    # having reached the proposal stage.
    return {"Closed lost": 2}.get(stage, STAGES.index(stage))


def pipeline_flow(deals: pd.DataFrame) -> dict[str, Any]:
    """Sankey of deal value from lead source, through plan, to outcome."""
    outcome = deals["stage"].map(
        lambda s: (
            "Won" if s == "Closed won" else "Lost" if s == "Closed lost" else "Open"
        )
    )
    first = deals.groupby(["source", "plan"])["amount"].sum().reset_index()
    second = (
        deals.assign(outcome=outcome)
        .groupby(["plan", "outcome"])["amount"]
        .sum()
        .reset_index()
    )
    links = [
        {"source": src, "target": dst, "value": round(value / 1_000, 1)}
        for frame in (first, second)
        for src, dst, value in zip(
            frame.iloc[:, 0], frame.iloc[:, 1], frame["amount"], strict=True
        )
        if value > 0
    ]
    nodes = [*SOURCES, *PLANS, "Won", "Open", "Lost"]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: ${c}K"},
        "series": [
            {
                "type": "sankey",
                "left": 4,
                "right": 64,
                "top": 8,
                "bottom": 8,
                "nodeWidth": 14,
                "nodeGap": 12,
                "layoutIterations": 0,
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {"color": "gradient", "curveness": 0.5},
                "itemStyle": {"borderRadius": 3},
                "data": [{"name": node} for node in nodes],
                "links": links,
            }
        ],
    }


def quota_gauge(bookings: float, quota: float, pace: float) -> dict[str, Any]:
    """Progress gauge of quarter-to-date bookings against quota."""
    attainment = bookings / quota * 100
    return {
        "series": [
            {
                "type": "gauge",
                "startAngle": 210,
                "endAngle": -30,
                "min": 0,
                "max": 100,
                "radius": "92%",
                "center": ["50%", "58%"],
                "progress": {"show": True, "roundCap": True, "width": 16},
                "axisLine": {"roundCap": True, "lineStyle": {"width": 16}},
                "pointer": {"show": False},
                "axisTick": {"show": False},
                "splitLine": {"show": False},
                "axisLabel": {"show": False},
                "anchor": {"show": False},
                "title": {"offsetCenter": [0, "32%"], "fontSize": 13},
                "detail": {
                    "valueAnimation": True,
                    "offsetCenter": [0, "-4%"],
                    "fontSize": 34,
                    "fontWeight": 650,
                    "formatter": "{value}%",
                },
                "data": [
                    {
                        "value": round(attainment),
                        "name": f"{money(bookings)} of {money(quota)} · pace {pace:.0f}%",
                    }
                ],
            }
        ],
    }


def pipeline_by_owner(totals: pd.Series) -> dict[str, Any]:
    """Selectable horizontal bars of open pipeline (in $K) per account executive."""
    source = totals.rename("pipeline").rename_axis("owner").reset_index()
    source["label"] = (source["pipeline"] * 1_000).map(money)
    source["pipeline"] = source["pipeline"].round()
    return {
        "dataset": {"source": source},
        "tooltip": {"trigger": "item"},
        "grid": {"left": 4, "right": 48, "top": 4, "bottom": 4},
        "xAxis": {
            "type": "value",
            "axisLabel": {"formatter": "${value}K"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "yAxis": {
            "type": "category",
            "axisTick": {"show": False},
        },
        "series": [
            {
                "name": "Open pipeline",
                "type": "bar",
                "barWidth": "58%",
                "selectedMode": "single",
                "select": {
                    "itemStyle": {
                        "borderWidth": 0,
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0, 0, 0, 0.2)",
                    }
                },
                "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                "label": {"show": True, "position": "right", "formatter": "{@label}"},
                "tooltip": {"formatter": "{b}: {@label} open"},
                "encode": {"x": "pipeline", "y": "owner"},
            }
        ],
    }
