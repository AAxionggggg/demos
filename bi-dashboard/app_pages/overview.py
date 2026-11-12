"""Overview: revenue KPIs and charts that load concurrently, layout first.

The main script paints the page layout right away: section headers, card
frames and titles, and an ``st.skeleton`` sized like each card's content. It
calls each card's ``@st.fragment(parallel=True)`` inside its skeleton, so the
fragments load concurrently and each one's first element replaces its
skeleton. Cached reruns update the cards in place without a skeleton.

A card with its own controls (MRR by plan) must draw them inside its fragment,
so that using them reruns only that card. It draws its frame, header, and
skeleton itself.
"""

from utils import charts, data
from utils.components import (
    account_columns,
    account_table,
    card_header,
    card_menu,
    open_clicked_account,
    section_header,
)
from utils.definitions import DEFINITIONS
from utils.formatting import change, money, signed_pct, signed_pts

import streamlit as st

# Each skeleton has the height of the content that replaces it, so nothing
# moves when the data arrives.
KPI_HEIGHT = 186
CHART_HEIGHT = 320
USAGE_HEIGHT = 260
DRILLDOWN_HEIGHT = 444  # The industry and top-accounts cards
KPIS = {
    "arr": ("Annual recurring revenue", ":material/payments:", "area"),
    "net_new_mrr": ("Net new MRR", ":material/trending_up:", "bar"),
    "nrr": ("Net revenue retention", ":material/autorenew:", "line"),
    "gross_churn": ("Monthly gross churn", ":material/trending_down:", "bar"),
}

filters = data.current_filters()


def export_csv() -> bytes:
    # Called only when the button is clicked, so the button renders before the
    # data has loaded.
    accounts, _ = data.load_book()
    return data.accounts_csv(data.filter_accounts(accounts, filters))


@st.fragment(parallel=True)
def kpi_card(kpi: str, filters: data.Filters) -> None:
    """One certified KPI. The page calls it inside its ``st.skeleton``."""
    accounts, history = data.load_book()
    ids = data.filter_accounts(accounts, filters).index
    series = data.monthly_kpis(history, ids, filters.months)[kpi]
    first, last = series.iloc[0], series.iloc[-1]
    window = f"vs. {filters.months} months ago"
    if kpi == "arr":
        value, delta, description = money(last), signed_pct(change(last, first)), window
    elif kpi == "net_new_mrr":
        average = series.iloc[1:-1].mean()
        value, delta = money(last), signed_pct(change(last, average))
        description = "vs. period average"
    elif kpi == "nrr":
        value, delta, description = f"{last:.1f}%", signed_pts(last - first), window
    else:
        value = f"{last:.1f}%"
        delta = signed_pts(last - series.iloc[1:].mean())
        description = "vs. period average"
    label, icon, chart_type = KPIS[kpi]
    st.metric(
        f"{label} :green[:material/verified:]",
        value,
        delta,
        delta_color="inverse" if kpi == "gross_churn" else "normal",
        delta_description=description,
        chart_data=series.iloc[1:],
        chart_type=chart_type,
        icon=icon,
        border=True,
        help=DEFINITIONS[kpi].measures,
        height=KPI_HEIGHT,
    )


@st.fragment(parallel=True)
def mrr_growth_card(filters: data.Filters) -> None:
    """MRR by plan, with a $/% view and a menu with forecast and comparison."""
    with st.container(border=True, height="stretch"):
        controls = card_header(
            "MRR by plan", "Monthly recurring revenue, stacked by plan", certified=True
        )
        view = controls.segmented_control(
            "View",
            ["$", "%"],
            default="$",
            required=True,
            key="growth_view",
            label_visibility="collapsed",
            help="Show absolute MRR or each plan's share",
        )
        card_menu(
            controls,
            "mrr_by_plan",
            {"mrr_forecast": "forecast", "mrr_compare": "last year"},
        )
        with st.skeleton(height=CHART_HEIGHT):
            accounts, history = data.load_book()
            region_accounts = accounts[accounts["region"].isin(filters.regions)]
            monthly = data.mrr_by_plan(history, region_accounts, filters.months)
            year_earlier = None
            if st.session_state.get("mrr_compare"):
                year_earlier = data.mrr_by_plan(
                    history, region_accounts, filters.months, years_back=1
                )
            st.echarts_chart(
                charts.mrr_growth(
                    monthly,
                    filters.plans,
                    share=view == "%",
                    forecast=data.mrr_forecast(monthly)
                    if st.session_state.get("mrr_forecast")
                    else None,
                    year_earlier=year_earlier,
                    milestones=data.milestones(filters),
                ),
                height=CHART_HEIGHT,
                alt="Monthly recurring revenue by plan over time; Enterprise contributes most",
            )


@st.fragment(parallel=True)
def mrr_bridge_chart(filters: data.Filters) -> None:
    accounts, history = data.load_book()
    ids = data.filter_accounts(accounts, filters).index
    movements = data.mrr_movements(history, ids, filters.months)
    st.echarts_chart(
        charts.mrr_bridge(movements),
        height=CHART_HEIGHT,
        alt=(
            f"MRR grew from {money(movements['start'])} to {money(movements['end'])}, "
            "mostly from expansion"
        ),
    )


@st.fragment(parallel=True)
def usage_chart(filters: data.Filters) -> None:
    matrix = data.usage_matrix(data.load_usage(), filters.regions)
    st.echarts_chart(
        charts.usage_heatmap(matrix),
        height=USAGE_HEIGHT,
        alt="Product sessions by weekday and UTC hour, busiest on weekday afternoons",
    )


@st.fragment
def industry_drilldown(filters: data.Filters) -> None:
    """Donut of MRR by industry that filters the top-accounts table on click.

    This is a regular (not parallel) fragment because a click in the table
    opens a dialog, and selecting a slice reruns only this section.
    """
    accounts, _ = data.load_book()
    accounts = data.filter_accounts(accounts, filters)
    active = accounts[accounts["mrr"] > 0]
    by_industry = (
        active.groupby("industry")["mrr"].sum().reindex(data.INDUSTRIES, fill_value=0)
    )

    mix_col, table_col = st.columns([2, 3])
    with mix_col.container(border=True, height="stretch"):
        controls = card_header(
            "Revenue by industry",
            "Click a slice to filter the accounts",
            certified=True,
        )
        card_menu(controls, "industry_mix")
        event = st.echarts_chart(
            charts.industry_mix(by_industry),
            on_select="rerun",
            height=CHART_HEIGHT + 40,
            alt="Share of MRR by industry",
        )

    selected = [
        data.INDUSTRIES[index]
        for group in event.selection.selected
        for index in group["data_indices"]
    ]
    top = active[active["industry"].isin(selected)] if selected else active
    top = top.nlargest(10, "mrr")

    with table_col.container(border=True, height="stretch"):
        controls = card_header(
            "Top accounts",
            f"{selected[0]} customers by MRR"
            if selected
            else "Largest customers by MRR",
        )
        if selected:
            controls.badge(selected[0], icon=":material/filter_alt:", color="primary")
        table = account_table(top)
        st.dataframe(
            table,
            column_config=account_columns(compact=True, key="top_accounts_click"),
            hide_index=True,
            height=CHART_HEIGHT + 40,
            alt="Top accounts by monthly recurring revenue",
        )
        open_clicked_account(table, "top_accounts_click")


actions = section_header(
    "Revenue",
    help="Certified metrics, owned by revenue operations and refreshed hourly.",
    sql="revenue",
)
actions.badge("Live", icon=":material/radio_button_checked:", color="green")
actions.download_button(
    "Export",
    export_csv,
    file_name="nimbus_accounts.csv",
    mime="text/csv",
    icon=":material/download:",
    on_click="ignore",
)

# The main script draws every skeleton, so the page has its final layout from
# the first paint. Each KPI's metric replaces its skeleton when its data arrives.
with st.container(horizontal=True):
    for kpi in KPIS:
        with st.skeleton(height=KPI_HEIGHT):
            kpi_card(kpi, filters)

growth_col, bridge_col = st.columns([3, 2])
with growth_col:
    mrr_growth_card(filters)
with bridge_col.container(border=True, height="stretch"):
    controls = card_header(
        "MRR bridge",
        f"How MRR moved over the last {filters.months} months",
        certified=True,
    )
    card_menu(controls, "mrr_bridge")
    with st.skeleton(height=CHART_HEIGHT):
        mrr_bridge_chart(filters)

with st.container(border=True):
    controls = card_header(
        "When customers use Nimbus",
        "Product sessions by weekday and hour (UTC) — shifts with the region filter",
        certified=True,
    )
    card_menu(controls, "usage")
    with st.skeleton(height=USAGE_HEIGHT):
        usage_chart(filters)

# A regular fragment runs in the main script and blocks it while it loads, so
# it comes last, after every parallel fragment has started.
with st.skeleton(height=DRILLDOWN_HEIGHT):
    industry_drilldown(filters)
