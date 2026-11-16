"""Activity: the audit log of every decision, and how far planners trust the agent."""

import pandas as pd
from utils import charts, rules, store, ui

import streamlit as st

CHART_HEIGHT = 280

decisions = store.load_decisions()
recent = decisions[
    decisions["decided_at"] >= pd.Timestamp.today() - pd.Timedelta(days=30)
]
approved = recent[recent["action"].str.startswith("Approved")]
edited = recent[recent["action"] == "Approved with changes"]
edit_size = (edited["final_qty"] / edited["agent_qty"] - 1).abs().median() * 100

with st.container(horizontal=True):
    st.metric(
        "Decisions",
        f"{len(recent):,}",
        f"{recent['reviewer'].nunique()} planners",
        delta_color="gray",
        delta_arrow="off",
        delta_description="last 30 days",
        icon=":material/fact_check:",
        border=True,
    )
    st.metric(
        "Ordered",
        rules.money(approved["value"].sum()),
        f"{len(approved):,} purchase orders",
        delta_color="gray",
        delta_arrow="off",
        icon=":material/local_shipping:",
        border=True,
    )
    st.metric(
        "Approved as proposed",
        f"{rules.acceptance(recent):.0%}",
        f"{len(edited) / max(len(recent), 1):.0%} changed",
        delta_color="gray",
        delta_arrow="off",
        icon=":material/smart_toy:",
        border=True,
    )
    st.metric(
        "Typical change",
        f"{edit_size:.0f}%",
        "when planners edit",
        delta_color="gray",
        delta_arrow="off",
        icon=":material/tune:",
        help="Median size of the quantity change on proposals approved with changes.",
        border=True,
    )

trend_col, category_col = st.columns([3, 2])
with trend_col.container(border=True, height="stretch"):
    ui.card_header("Decisions per day", "Agent proposals by outcome")
    st.echarts_chart(
        charts.decisions_per_day(recent),
        height=CHART_HEIGHT,
        alt="Decisions per day by outcome, with more approved as proposed lately",
    )
with category_col.container(border=True, height="stretch"):
    ui.card_header(
        "Where the agent is trusted",
        "Share of proposals approved without changes",
    )
    st.echarts_chart(
        charts.acceptance_by_category(recent),
        height=CHART_HEIGHT,
        alt="Share of proposals approved unchanged in each category",
    )

with st.container(border=True):
    controls = ui.card_header(
        "Audit log",
        "Every decision, newest first, with the agent's and the final quantity",
    )
    log = pd.DataFrame(
        {
            "decided_at": decisions["decided_at"],
            "po": decisions["proposal_id"],
            "product": decisions["product"],
            "location": decisions["location"],
            "reviewer": decisions["reviewer"],
            "action": decisions["action"].map(lambda action: [action]),
            "agent_qty": decisions["agent_qty"],
            "final_qty": decisions["final_qty"],
            "change": (decisions["final_qty"] / decisions["agent_qty"] - 1) * 100,
            "value": decisions["value"] / 1e3,
            "note": decisions["note"].fillna(""),
        }
    )
    controls.download_button(
        "Export",
        log.assign(action=decisions["action"], value=decisions["value"]).to_csv(
            index=False
        ),
        file_name="cairn_reorder_audit_log.csv",
        mime="text/csv",
        icon=":material/download:",
        on_click="ignore",
    )
    st.dataframe(
        log,
        column_config={
            "decided_at": st.column_config.DatetimeColumn(
                "Decided", format="MMM D, h:mm a", pinned=True
            ),
            "po": "PO",
            "product": "Product",
            "location": "Location",
            "reviewer": "Reviewer",
            "action": st.column_config.MultiselectColumn(
                "Decision",
                options=list(ui.ACTION_BADGES),
                color=list(ui.ACTION_BADGES.values()),
            ),
            "agent_qty": st.column_config.NumberColumn("Agent qty", format="localized"),
            "final_qty": st.column_config.NumberColumn("Final qty", format="localized"),
            "change": st.column_config.NumberColumn("Change", format="%+.0f%%"),
            "value": st.column_config.NumberColumn("Value", format="$%.1fk"),
            "note": st.column_config.TextColumn("Note", width="large"),
        },
        hide_index=True,
        height=420,
        alt="Audit log of planner decisions on agent proposals",
    )
