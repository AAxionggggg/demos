"""Pricing: where profit peaks as price and marketing change.

The price-response curve reruns the season simulation at every price from
-25% to +25%, and the profit surface at every price and marketing pair.
Clicking a cell of the surface applies its levers through the chart's
``on_select`` callback.
"""

import functools

from utils import charts, model, ui

import streamlit as st

CURVE_HEIGHT = 320
SURFACE_HEIGHT = 420
KPI_HEIGHT = 136

levers = ui.current_levers()
product = model.PRODUCTS[levers.product]


@st.fragment(parallel=True)
def best_price_metrics(levers: model.Levers) -> None:
    curve = model.price_response(levers)
    best = curve.loc[curve["profit"].idxmax()]
    now = curve.loc[curve["price_change"] == levers.price_change].iloc[0]
    with st.container(horizontal=True):
        st.metric(
            "Profit-maximizing price",
            f"${best['price']:,.0f}",
            f"{best['price_change']:+.0f}% vs. list",
            delta_color="off",
            delta_arrow="off",
            icon=":material/sell:",
            border=True,
            height=KPI_HEIGHT,
        )
        st.metric(
            "Profit at that price",
            ui.money(best["profit"]),
            ui.signed_money(best["profit"] - now["profit"]),
            delta_description="vs. current price",
            icon=":material/savings:",
            border=True,
            height=KPI_HEIGHT,
        )
        st.metric(
            "Units at that price",
            f"{best['units']:,.0f}",
            ui.signed_pct(ui.pct_change(best["units"], now["units"])),
            delta_description="vs. current price",
            delta_color="off",
            icon=":material/shopping_bag:",
            border=True,
            height=KPI_HEIGHT,
        )
        st.metric(
            "Price elasticity",
            f"{product.elasticity:.1f}",
            icon=":material/ssid_chart:",
            help=f"A 1% higher price sells about {abs(product.elasticity):.1f}% fewer "
            "units. The simulations also vary it by ±12% to cover fitting error.",
            border=True,
            height=KPI_HEIGHT,
        )


@st.fragment(parallel=True)
def price_curve_chart(levers: model.Levers) -> None:
    st.echarts_chart(
        charts.price_curve(model.price_response(levers), levers.price_change),
        height=CURVE_HEIGHT,
        alt=f"Median season profit by price for {levers.product.lower()}, "
        "with the current and best prices marked",
    )


def apply_cell(key: str, levers: model.Levers) -> None:
    """Apply the price and marketing of the clicked surface cell."""
    surface = model.profit_surface(levers)
    indices = [
        index
        for group in st.session_state[key].selection.selected
        for index in group["data_indices"]
    ]
    if not indices:
        return
    cell = surface.iloc[indices[0]]
    st.session_state.price = int(cell["price_change"])
    st.session_state.marketing = float(cell["spend"])
    st.toast(
        f"Applied price **{cell['price']}** and marketing **{cell['marketing']}** "
        "per week",
        icon=":material/check:",
    )


with st.skeleton(height=KPI_HEIGHT):
    best_price_metrics(levers)

with st.container(border=True):
    ui.card_header(
        "Price response",
        f"Median season profit at each price, list price ${product.price:,.0f}",
        help="Each point is a full season simulation at that price, with the other "
        "levers unchanged. When supply runs short, a higher price loses fewer "
        "units than the elasticity alone suggests.",
    )
    with st.skeleton(height=CURVE_HEIGHT):
        price_curve_chart(levers)

with st.container(border=True):
    ui.card_header(
        "Profit surface",
        "Median season profit by price and weekly marketing. Click a cell to apply it.",
        help="143 season simulations, one per cell, with the promo and supply "
        "levers unchanged.",
    )
    # The surface runs in the main script, so a click reruns the whole app and
    # the sidebar levers show the applied values. The key changes with the
    # levers, so a new scenario starts without a selected cell.
    key = (
        f"surface-{levers.product}-{levers.price_change}-{levers.marketing}-"
        f"{levers.promo_discount}-{levers.promo_window}-{levers.supply}-"
        f"{levers.uncertainty}"
    )
    with st.skeleton(height=SURFACE_HEIGHT):
        st.echarts_chart(
            charts.profit_surface(
                model.profit_surface(levers), levers.price_change, levers.marketing
            ),
            height=SURFACE_HEIGHT,
            key=key,
            on_select=functools.partial(apply_cell, key, levers),
            alt="Heatmap of median season profit by price and weekly marketing spend",
        )
