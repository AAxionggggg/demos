"""Accounts: a searchable customer book with a brushable scatter plot.

The cards cross-filter (brushing the scatter plot filters the table), so they
share one load instead of running as independent fragments. The page still
paints its layout first: it draws every card's frame, header, and skeleton,
then loads the book once and fills each card. On reruns, such as typing in the
search box, each skeleton keeps the previous table mounted until its new
content arrives, so the tables update in place.
"""

from datetime import date, timedelta

import pandas as pd
from streamlit_pivot import st_pivot_table
from utils import charts, data
from utils.components import (
    STATUS_ICONS,
    account_columns,
    account_table,
    card_header,
    card_menu,
    open_clicked_account,
    section_header,
)

import streamlit as st

CARD_HEIGHT = 340
TABLE_HEIGHT = 460

# The pivot only handles scalar columns, so list-valued fields such as
# products and the MRR trend are left out.
PIVOT_FIELDS = {
    "name": "Account",
    "region": "Region",
    "industry": "Industry",
    "plan": "Plan",
    "status": "Status",
    "owner": "Owner",
    "customer_since": "Customer since",
    "renewal_date": "Renewal",
    "mrr": "MRR",
    "seats": "Seats",
    "health": "Health",
    "nps": "NPS",
}


@st.dialog("Explore accounts", width="large", icon=":material/pivot_table_chart:")
def explore_accounts(accounts: pd.DataFrame) -> None:
    st.caption(
        f"{len(accounts)} accounts matching the current filters. Drag fields between "
        "rows, columns, and values, or click a cell to list the accounts behind it."
    )
    # A named index would show up as an extra pivot field, so drop it.
    source = accounts[list(PIVOT_FIELDS)].rename(columns=PIVOT_FIELDS)
    st_pivot_table(
        source.reset_index(drop=True),
        key="accounts_pivot",
        rows=["Region", "Industry"],
        columns=["Plan"],
        values=["MRR", "Health"],
        aggregation={"MRR": "sum", "Health": "avg"},
        number_format={
            "MRR": "$,.0f",
            "Health": ",.0f",
            "Seats": ",.0f",
            "NPS": ",.0f",
        },
        show_subtotals=True,
        row_sort={"by": "value", "direction": "desc", "value_field": "MRR"},
        sorters={"Plan": data.PLANS, "Status": data.STATUSES},
        filter_fields=["Status", "Owner"],
        conditional_formatting=[
            {"type": "data_bars", "apply_to": ["MRR"], "fill": "gradient"}
        ],
        export_filename="nimbus_accounts",
        max_height=520,
    )


filters = data.current_filters()

actions = section_header(
    "Customer book",
    help="Every account with its plan, revenue, health, and renewal date.",
    sql="accounts",
)

with st.container(horizontal=True, vertical_alignment="center"):
    query = st.text_input(
        "Search accounts",
        type="search",
        placeholder="Search by account, owner, or industry",
        live=True,
        label_visibility="collapsed",
        key="account_search",
    )
    statuses = st.pills(
        "Status",
        data.STATUSES,
        selection_mode="multi",
        default=data.STATUSES[:3],
        format_func=lambda status: f"{STATUS_ICONS[status]} {status}",
        key="account_status",
        label_visibility="collapsed",
        width="content",
    )


def matching_accounts(accounts: pd.DataFrame) -> pd.DataFrame:
    """Apply the global filters, the status pills, and the search box."""
    accounts = data.filter_accounts(accounts, filters)
    accounts = accounts[accounts["status"].isin(statuses or data.STATUSES)]
    if query:
        haystack = (
            accounts["name"] + " " + accounts["owner"] + " " + accounts["industry"]
        )
        accounts = accounts[haystack.str.contains(query, case=False, regex=False)]
    return accounts


def export_csv() -> bytes:
    # Called only when the button is clicked, so the button renders before the
    # data has loaded.
    accounts, _ = data.load_book()
    return data.accounts_csv(matching_accounts(accounts))


actions.download_button(
    "Export",
    export_csv,
    file_name="nimbus_accounts.csv",
    mime="text/csv",
    icon=":material/download:",
    on_click="ignore",
)

# Layout first: draw every card's frame, header, and skeleton before loading.
scatter_col, renewals_col = st.columns([3, 2])
scatter_card = scatter_col.container(border=True, height="stretch")
with scatter_card:
    controls = card_header(
        "Health vs. revenue",
        "Bubble size shows seats. Use the select tool to filter the table.",
        certified=True,
    )
    card_menu(controls, "health_scatter")

with renewals_col.container(border=True, height="stretch"):
    renewals_controls = card_header("Upcoming renewals", "Next 90 days, soonest first")
    renewals_slot = st.skeleton(height=CARD_HEIGHT)

with st.container(border=True):
    table_controls = card_header("All accounts", "Sorted by MRR, largest first")
    table_badge = table_controls.empty()
    open_pivot = table_controls.button(
        "Pivot",
        icon=":material/pivot_table_chart:",
        help="Explore these accounts in a pivot table",
    )
    table_slot = st.skeleton(height=TABLE_HEIGHT)

# The scatter plot loads the book inside its own skeleton, so the loader's
# spinner text labels it. The other skeletons fill once that load finishes.
with scatter_card, st.skeleton(height=CARD_HEIGHT):
    book, _ = data.load_book()
    accounts = matching_accounts(book)
    event = st.echarts_chart(
        charts.health_scatter(accounts),
        on_select="rerun",
        # No key: a keyed chart would keep its brush indices when the search
        # changes the data, so they would point at different accounts.
        height=CARD_HEIGHT,
        alt="Account health score against MRR by plan; most revenue sits in healthy accounts",
    )

# Brush selections come back as indices into each plan's series.
brushed: list[str] = []
for group in event.selection.selected:
    plan_ids = accounts.index[accounts["plan"] == data.PLANS[group["series_index"]]]
    brushed += [plan_ids[index] for index in group["data_indices"]]

horizon = date.today() + timedelta(days=90)
renewals = accounts[(accounts["renewal_date"] <= horizon) & (accounts["mrr"] > 0)]
renewals_controls.badge(f"{len(renewals)} accounts", color="gray")
renewal_table = account_table(renewals.sort_values("renewal_date"))[
    ["view", "name", "renewal_date", "mrr"]
]
renewals_slot.dataframe(
    renewal_table,
    column_config=account_columns(key="renewal_click"),
    hide_index=True,
    height=CARD_HEIGHT,
    alt="Accounts renewing in the next 90 days",
)
open_clicked_account(renewal_table, "renewal_click")

table_accounts = accounts.loc[brushed] if brushed else accounts
if brushed:
    table_badge.badge(
        f"Scatter selection · {len(table_accounts)} of {len(accounts)}",
        icon=":material/select_all:",
        color="primary",
    )
else:
    table_badge.badge(f"{len(accounts)} accounts", color="gray")
if open_pivot:
    explore_accounts(table_accounts)
table = account_table(table_accounts.sort_values("mrr", ascending=False))
table_slot.dataframe(
    table,
    column_config=account_columns(key="account_click"),
    hide_index=True,
    height=TABLE_HEIGHT,
    alt="All customer accounts",
)
open_clicked_account(table, "account_click")
