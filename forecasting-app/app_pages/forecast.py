"""Forecast: the simulated season under the current levers, compared with the plan.

The main script paints the layout first: card frames, titles, and an
``st.skeleton`` sized like each card's content. Each card is an
``@st.fragment(parallel=True)``, so the cards load concurrently. They share
one cached simulation per scenario, so a lever change computes it once.
"""

from typing import Literal

import numpy as np
from utils import charts, model, ui

import streamlit as st

KPI_HEIGHT = 178
FAN_HEIGHT = 380
CARD_HEIGHT = 270
KPIS: dict[str, tuple[str, str, str, Literal["line", "bar", "area"], str]] = {
    "units": (
        "Units sold",
        ":material/shopping_bag:",
        "sales_p50",
        "bar",
        "Median (P50) units sold over the 26 weeks, capped by supply.",
    ),
    "revenue": (
        "Revenue",
        ":material/payments:",
        "revenue_p50",
        "area",
        "Median (P50) season revenue, after promo discounts.",
    ),
    "profit": (
        "Profit",
        ":material/savings:",
        "profit_p50",
        "area",
        "Median (P50) revenue minus product cost and marketing spend.",
    ),
    "stockout_risk": (
        "Stockout risk",
        ":material/inventory_2:",
        "stockout_risk",
        "bar",
        "Share of simulated seasons where demand outruns supply in at least one "
        "week. The sparkline shows the risk per week.",
    ),
}

levers = ui.current_levers()


@st.fragment(parallel=True)
def kpi_card(kpi: str, levers: model.Levers) -> None:
    forecast = model.simulate(levers)
    current, plan = forecast.summary, model.simulate(model.plan_for(levers)).summary
    label, icon, column, chart_type, help = KPIS[kpi]
    if kpi == "stockout_risk":
        value = f"{current.stockout_risk:.0%}"
        change = (current.stockout_risk - plan.stockout_risk) * 100
        delta = f"{change:+.0f} pts"
    else:
        value = (
            f"{current.units:,.0f}"
            if kpi == "units"
            else ui.money(getattr(current, kpi))
        )
        change = ui.pct_change(getattr(current, kpi), getattr(plan, kpi))
        delta = ui.signed_pct(change)
    on_plan = abs(change) < 0.05
    st.metric(
        label,
        value,
        "On plan" if on_plan else delta,
        delta_color="gray"
        if on_plan
        else "inverse"
        if kpi == "stockout_risk"
        else "normal",
        delta_arrow="off" if on_plan else "auto",
        delta_description=None if on_plan else "vs. plan",
        icon=icon,
        chart_data=forecast.weekly[column],
        chart_type=chart_type,
        help=help,
        border=True,
        height=KPI_HEIGHT,
    )


@st.fragment(parallel=True)
def fan_card(levers: model.Levers) -> None:
    """The weekly forecast with its own Units / Revenue control."""
    with st.container(border=True, height="stretch"):
        controls = ui.card_header(
            "Weekly forecast",
            f"Median and 50% / 80% ranges of {levers.simulations:,} simulated seasons",
        )
        metric = controls.segmented_control(
            "Measure",
            ["Units", "Revenue"],
            default="Units",
            required=True,
            key="fan_metric",
            label_visibility="collapsed",
        )
        with st.skeleton(height=FAN_HEIGHT):
            history = model.load_history(levers.product)
            st.echarts_chart(
                charts.fan_chart(
                    history,
                    model.simulate(levers),
                    metric=metric,
                    promo=levers.promo_window if levers.promo_discount else None,
                ),
                height=FAN_HEIGHT,
                alt=(
                    f"Weekly {metric.lower()} forecast for {levers.product.lower()} "
                    "with uncertainty bands, recent actuals, and last year"
                ),
            )


@st.fragment(parallel=True)
def brief_body(levers: model.Levers) -> None:
    with st.container(gap="medium"):
        for icon, text in ui.brief(levers):
            with st.container(horizontal=True, gap="small", wrap=False):
                st.markdown(f":primary[{icon}]", width="content")
                st.markdown(text)


@st.fragment(parallel=True)
def outcomes_chart(levers: model.Levers) -> None:
    forecast = model.simulate(levers)
    target = model.revenue_target(levers)
    st.echarts_chart(
        charts.outcome_histogram(forecast.outcomes, target),
        height=CARD_HEIGHT,
        alt=f"Distribution of simulated season revenue against the {ui.money(target)} target",
    )


@st.fragment(parallel=True)
def tornado_chart(levers: model.Levers) -> None:
    st.echarts_chart(
        charts.tornado(model.sensitivity(levers)),
        height=CARD_HEIGHT,
        alt="Change in median season profit when each lever moves down or up",
    )


with st.container(horizontal=True):
    for kpi in KPIS:
        with st.skeleton(height=KPI_HEIGHT):
            kpi_card(kpi, levers)

fan_col, brief_col = st.columns([3, 2])
with fan_col:
    fan_card(levers)
with brief_col.container(border=True, height="stretch"):
    ui.card_header(
        "Forecast brief",
        "What the simulations say about this scenario",
        help="Computed from the same simulations as the charts: the plan, this "
        "scenario without its promo, and the lever sensitivity.",
    )
    with st.skeleton(height=FAN_HEIGHT - 20):
        brief_body(levers)

outcomes_col, tornado_col = st.columns(2)
with outcomes_col.container(border=True, height="stretch"):
    target = model.revenue_target(levers)
    beat = float(np.mean(model.simulate(levers).outcomes["revenue"] >= target))
    ui.card_header(
        "Season revenue outcomes",
        f"{beat:.0%} of simulated seasons reach the {ui.money(target)} target",
        help="The target is the plan's median revenue plus 4%.",
    )
    with st.skeleton(height=CARD_HEIGHT):
        outcomes_chart(levers)
with tornado_col.container(border=True, height="stretch"):
    ui.card_header(
        "What moves profit",
        "Median profit change when each lever moves down or up",
        help="Price ±5 pts, promo ±10 pts, marketing ×0.5 / ×1.5, supply ±15 pts. "
        "Every run uses the same simulated futures, so the differences come from "
        "the levers alone.",
    )
    with st.skeleton(height=CARD_HEIGHT):
        tornado_chart(levers)
