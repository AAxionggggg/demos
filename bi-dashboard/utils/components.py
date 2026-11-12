"""Shared UI pieces for the Nimbus BI demo: headers, card menus, and drawers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

import streamlit as st
from utils import charts, data
from utils.definitions import DEFINITIONS
from utils.formatting import change, money, signed_pct

if TYPE_CHECKING:
    import pandas as pd

    from streamlit.delta_generator import DeltaGenerator

BadgeColor: TypeAlias = Literal[
    "red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"
]

STATUS_COLORS: dict[str, BadgeColor] = {
    "Healthy": "green",
    "Needs attention": "yellow",
    "At risk": "red",
    "Churned": "gray",
}
STATUS_ICONS = {
    "Healthy": ":material/check_circle:",
    "Needs attention": ":material/error:",
    "At risk": ":material/warning:",
    "Churned": ":material/do_not_disturb_on:",
}
PLAN_COLORS: dict[str, BadgeColor] = {
    "Starter": "gray",
    "Pro": "blue",
    "Enterprise": "violet",
}
STAGE_COLORS: dict[str, BadgeColor] = {
    "Prospecting": "gray",
    "Discovery": "blue",
    "Proposal": "violet",
    "Negotiation": "orange",
    "Closed won": "green",
    "Closed lost": "red",
}

VIEW_ACTION = ":material/side_navigation: View"
# Marks a certified metric, like a verified badge in a BI tool.
VERIFIED = ":green-badge[:material/verified:]"
_CARD_ACTIONS = {
    "measured": ":material/menu_book: What's measured",
    "sql": ":material/data_object: SQL query",
    "feedback": ":material/rate_review: Feedback",
}


def section_header(
    title: str, *, help: str | None = None, sql: str | None = None
) -> DeltaGenerator:
    """Render a section title and return a right-aligned container for actions.

    With ``sql``, the section's query from ``DEFINITIONS`` opens from a popover.
    """
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(title, help=help, anchor=False)
        actions = st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            width="content",
        )
    if sql:
        with actions.popover("SQL", icon=":material/data_object:", type="tertiary"):
            st.caption(f"Query behind **{DEFINITIONS[sql].title}**")
            st.code(DEFINITIONS[sql].sql, language="sql", width=560)
    return actions


def card_header(
    title: str,
    caption: str | None = None,
    *,
    certified: bool = False,
    help: str | None = None,
) -> DeltaGenerator:
    """Render a card title row and return a right-aligned container for controls."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        with st.container(gap=None):
            st.markdown(
                f"**{title}** {VERIFIED}" if certified else f"**{title}**", help=help
            )
            if caption:
                st.caption(caption)
        controls = st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            width="content",
        )
    return controls


def card_menu(
    controls: DeltaGenerator, card: str, toggles: dict[str, str] | None = None
) -> None:
    """Add a ⋮ menu with the card's definition, SQL query, and a feedback form.

    ``toggles`` maps Session State keys to option labels such as ``"forecast"``.
    Picking one flips its flag in the menu's callback, so the card already reads
    the new value when it redraws, and the option shows "Show" or "Hide".
    """
    toggles = toggles or {}
    key = f"{card}_menu"

    def label(option: str) -> str:
        if option in toggles:
            if st.session_state.get(option, False):
                return f":material/visibility_off: Hide {toggles[option]}"
            return f":material/add_chart: Show {toggles[option]}"
        return _CARD_ACTIONS[option]

    def flip_toggle() -> None:
        if st.session_state[key] in toggles:
            flag = st.session_state[key]
            st.session_state[flag] = not st.session_state.get(flag, False)

    # A label that is only a menu icon (with no ``icon``) hides the chevron.
    choice = controls.menu_button(
        ":material/more_vert:",
        [*toggles, *_CARD_ACTIONS],
        format_func=label,
        type="tertiary",
        key=key,
        help="More options",
        on_click=flip_toggle,
    )
    if choice == "measured":
        definition_drawer(card)
    elif choice == "sql":
        sql_dialog(card)
    elif choice == "feedback":
        feedback_dialog(card)


@st.dialog("What's measured", position="right", width=520, icon=":material/menu_book:")
def definition_drawer(card: str) -> None:
    definition = DEFINITIONS[card]
    st.subheader(definition.title, anchor=False)
    with st.container(horizontal=True, gap="small"):
        st.badge("Certified", icon=":material/verified:", color="green")
        st.badge(definition.owner, icon=":material/groups:", color="gray")
        st.badge(definition.refresh, icon=":material/update:", color="gray")
    st.markdown(definition.measures)
    st.markdown("**Query**")
    st.code(definition.sql, language="sql")


@st.dialog("SQL query", width="medium", icon=":material/data_object:")
def sql_dialog(card: str) -> None:
    definition = DEFINITIONS[card]
    st.caption(
        f"Query behind **{definition.title}**, refreshed {definition.refresh.lower()}"
    )
    st.code(definition.sql, language="sql")


@st.dialog("Feedback", icon=":material/rate_review:")
def feedback_dialog(card: str) -> None:
    definition = DEFINITIONS[card]
    st.markdown(f"Is **{definition.title}** correct and useful?")
    rating = st.feedback("thumbs", key=f"{card}_rating")
    st.text_area(
        "Comment",
        placeholder="What's missing or looks wrong?",
        key=f"{card}_comment",
    )
    if st.button("Send", type="primary", disabled=rating is None, key=f"{card}_send"):
        st.toast(f"Thanks! {definition.owner} will review it.", icon=":material/check:")
        st.rerun()


def account_columns(*, compact: bool = False, key: str) -> dict[str, Any]:
    """Column configuration for account tables, with a drawer button column."""
    columns: dict[str, Any] = {
        "view": st.column_config.ButtonColumn(
            "",
            type="tertiary",
            pinned=True,
            key=key,
            help="Open account details",
        ),
        "name": st.column_config.TextColumn("Account", pinned=True),
        "plan": st.column_config.MultiselectColumn(
            "Plan", options=data.PLANS, color=[PLAN_COLORS[p] for p in data.PLANS]
        ),
        "mrr": st.column_config.NumberColumn("MRR", format="$%,d"),
        "mrr_trend": st.column_config.AreaChartColumn(
            "Trend", color="auto", y_min=0, width="small"
        ),
        "health": st.column_config.ProgressColumn(
            "Health",
            min_value=0,
            max_value=100,
            format="%d",
            color="auto",
            width="small",
        ),
        "status": st.column_config.MultiselectColumn(
            "Status",
            options=data.STATUSES,
            color=[STATUS_COLORS[s] for s in data.STATUSES],
        ),
        "products": st.column_config.MultiselectColumn(
            "Products", options=data.PRODUCTS, color="auto"
        ),
        "region": st.column_config.TextColumn("Region"),
        "industry": st.column_config.TextColumn("Industry"),
        "seats": st.column_config.NumberColumn("Seats", format="localized"),
        "owner": st.column_config.TextColumn("Owner"),
        "renewal_date": st.column_config.DateColumn("Renewal", format="MMM D, YYYY"),
    }
    if compact:
        for column in ("status", "region", "industry", "seats", "owner", "products"):
            columns[column] = None
    return columns


def account_table(accounts: pd.DataFrame) -> pd.DataFrame:
    """Shape accounts for display: list-valued badge columns and a view button."""
    table = accounts.copy()
    table["view"] = VIEW_ACTION
    table["plan"] = table["plan"].map(lambda value: [value])
    table["status"] = table["status"].map(lambda value: [value])
    order = ["view", "name", "plan", "mrr", "mrr_trend", "health", "status", "products"]
    rest = ["region", "industry", "seats", "owner", "renewal_date"]
    return table[order + rest]


def open_clicked_account(table: pd.DataFrame, key: str) -> None:
    """Open the account drawer when a view button in ``table`` was clicked."""
    click = st.session_state.get(key)
    if click is not None:
        account_drawer(table.index[click.row])


@st.dialog("Account details", position="right", width=560, icon=":material/domain:")
def account_drawer(account_id: str) -> None:
    accounts, history = data.load_book()
    account = accounts.loc[account_id].to_dict()

    st.subheader(account["name"], anchor=False)
    with st.container(horizontal=True, gap="small"):
        st.badge(
            account["plan"],
            icon=":material/workspace_premium:",
            color=PLAN_COLORS[account["plan"]],
        )
        st.badge(account["region"], icon=":material/public:", color="gray")
        st.badge(
            account["status"],
            icon=STATUS_ICONS[account["status"]],
            color=STATUS_COLORS[account["status"]],
        )

    mrr_history = history.loc[[account_id]].iloc[0]
    three_months_ago = float(mrr_history.iloc[-4])
    mrr_col, seats_col, health_col = st.columns(3)
    mrr_col.metric(
        "MRR",
        money(account["mrr"]),
        signed_pct(change(account["mrr"], three_months_ago)),
        delta_description="vs. 3 months ago",
        border=True,
        height="stretch",
    )
    seats_col.metric("Seats", f"{account['seats']:,}", border=True, height="stretch")
    health_col.metric(
        "Health", f"{account['health']}/100", border=True, height="stretch"
    )

    with st.container(border=True):
        st.markdown("**MRR history**")
        st.echarts_chart(
            charts.account_mrr(mrr_history),
            height=200,
            alt=f"Monthly recurring revenue history for {account['name']}",
        )

    with st.container(border=True):
        st.markdown("**Product adoption**")
        peers = accounts[accounts["plan"] == account["plan"]]
        plan_average = [
            sum(values) / len(peers) for values in zip(*peers["adoption"], strict=True)
        ]
        st.echarts_chart(
            charts.product_adoption(account["adoption"], plan_average),
            height=280,
            alt=f"Product adoption of {account['name']} compared with the {account['plan']} plan average",
        )

    products = " ".join(f":violet-badge[{product}]" for product in account["products"])
    st.table(
        {
            ":material/person: Customer success": account["owner"],
            ":material/factory: Industry": account["industry"],
            ":material/calendar_month: Customer since": account[
                "customer_since"
            ].strftime("%b %d, %Y"),
            ":material/event_repeat: Renewal": account["renewal_date"].strftime(
                "%b %d, %Y"
            ),
            ":material/sentiment_satisfied: NPS": str(account["nps"]),
            ":material/widgets: Products": products,
        },
        border="horizontal",
        alt=f"Key facts about {account['name']}",
    )

    with st.container(horizontal=True, horizontal_alignment="right"):
        action = st.menu_button(
            "Actions",
            [
                ":material/event: Schedule QBR",
                ":material/mail: Email champion",
                ":material/flag: Flag for review",
            ],
            icon=":material/bolt:",
            key="drawer_actions",
        )
        if st.button("Done", type="primary", key="drawer_done"):
            st.rerun()
    if action:
        st.toast(
            f"{action.split(': ', 1)[1]} · {account['name']}", icon=":material/check:"
        )
