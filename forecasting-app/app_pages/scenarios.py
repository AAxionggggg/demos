"""Scenarios: saved what-ifs side by side, with their spread of outcomes."""

import pandas as pd
from utils import charts, model, ui

import streamlit as st

CHART_HEIGHT = 320
LOAD = ":material/upload: Load"
DELETE = ":material/delete: Delete"

levers = ui.current_levers()
scenarios = ui.saved_scenarios(levers.product)
plan = model.simulate(model.plan_for(levers)).summary


def handle_action() -> None:
    click = st.session_state.scenario_action
    name, saved = scenarios[click.row]
    if click.label == LOAD:
        # The levers are shared by every page, so the loaded scenario shows up
        # here as "Current" and on the other pages.
        ui.apply_levers(saved)
        st.toast(f"Loaded **{name}** into the levers", icon=":material/upload:")
    else:
        del scenarios[click.row]
        st.toast(f"Deleted **{name}**", icon=":material/delete:")


rows = []
for name, saved in scenarios:
    forecast = model.simulate(saved)
    summary = forecast.summary
    rows.append(
        {
            "actions": [LOAD, DELETE],
            "name": name,
            "levers": saved.describe(),
            "units": round(summary.units),
            "revenue": summary.revenue / 1e6,
            "profit": summary.profit / 1e6,
            "vs_plan": ui.pct_change(summary.profit, plan.profit),
            "stockout_risk": summary.stockout_risk * 100,
            "weekly_units": forecast.weekly["sales_p50"].round().tolist(),
        }
    )
table = pd.DataFrame(rows)

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader(f"{model.PRODUCTS[levers.product].description}", anchor=False)
    with st.container(horizontal=True, horizontal_alignment="right", width="content"):
        st.download_button(
            "Export",
            table.drop(columns=["actions", "weekly_units"])
            .rename(columns={"revenue": "revenue_musd", "profit": "profit_musd"})
            .to_csv(index=False),
            file_name=f"cairn_{levers.product.lower()}_scenarios.csv",
            mime="text/csv",
            icon=":material/download:",
            on_click="ignore",
            disabled=table.empty,
        )

if table.empty:
    st.info(
        "Set the levers and select **Save scenario** to compare scenarios here.",
        icon=":material/bookmark_add:",
    )
    st.stop()

with st.container(border=True):
    ui.card_header(
        "Saved scenarios",
        f"Median outcomes of {levers.simulations:,} simulated seasons each. "
        "Load one to edit its levers.",
    )
    st.dataframe(
        table,
        column_config={
            "actions": st.column_config.ButtonColumn(
                "",
                type="tertiary",
                pinned=True,
                key="scenario_action",
                on_click=handle_action,
                help="Load or delete this scenario",
            ),
            "name": st.column_config.TextColumn("Scenario", pinned=True),
            "levers": st.column_config.TextColumn("Levers", width="medium"),
            "units": st.column_config.NumberColumn("Units", format="localized"),
            "revenue": st.column_config.NumberColumn("Revenue", format="$%.2fM"),
            "profit": st.column_config.NumberColumn("Profit", format="$%.2fM"),
            "vs_plan": st.column_config.NumberColumn(
                "Profit vs. plan", format="%+.1f%%"
            ),
            "stockout_risk": st.column_config.ProgressColumn(
                "Stockout risk",
                min_value=0,
                max_value=100,
                format="%.0f%%",
                width="small",
            ),
            "weekly_units": st.column_config.LineChartColumn(
                "Weekly units", width="medium", y_min=0
            ),
        },
        hide_index=True,
        alt="Saved scenarios with their median units, revenue, profit, and risk",
    )
    st.caption(f"Current levers: {levers.describe()}")

compared = [(name, saved) for name, saved in scenarios]
if levers not in [saved for _, saved in scenarios]:
    compared.append(("Current", levers))

spread_col, weekly_col = st.columns(2)
with spread_col.container(border=True, height="stretch"):
    ui.card_header(
        "Risk and reward",
        "Season profit across simulations: box P25–P75, whiskers P5–P95",
    )
    st.echarts_chart(
        charts.scenario_boxplot(
            [
                (name, model.simulate(saved).outcomes["profit"].to_numpy())
                for name, saved in compared
            ]
        ),
        height=CHART_HEIGHT,
        alt="Spread of simulated season profit for each scenario",
    )
with weekly_col.container(border=True, height="stretch"):
    ui.card_header("Weekly units", "Median units sold per week")
    weekly = pd.DataFrame(
        {
            name: model.simulate(saved).weekly["sales_p50"].to_numpy()
            for name, saved in compared
        },
        index=pd.Index(model.forecast_weeks(), name="week"),
    ).round()
    st.echarts_chart(
        charts.scenario_lines(weekly),
        height=CHART_HEIGHT,
        alt="Median weekly units sold for each scenario",
    )

best_name, best = max(compared, key=lambda item: model.simulate(item[1]).summary.profit)
gap = model.simulate(best).summary.profit - model.simulate(levers).summary.profit
if best != levers and gap > 0:
    st.caption(
        f":material/lightbulb: **{best_name}** has the highest median profit, "
        f"{ui.money(gap)} more than the current levers."
    )
