"""Rendering for Cairn Analyst: messages, the agent's steps, results, and the canvas."""

from __future__ import annotations

import inspect
import os
import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from utils import agent, charts, data, pricing
from utils.files import Attachment, Profile
from utils.format import money, pct

STATIC = Path(__file__).parent.parent / "static"
AVATAR = str(STATIC / "icon.svg")
CURSOR = ":primary[▍]"
PACES = {"Natural": 0.45, "Instant": 0.0}
CANVAS_KINDS = {"revenue", "pricing", "restock", "summary", "file"}

COLUMNS: dict[str, Any] = {
    "channel": st.column_config.TextColumn("Channel"),
    "category": st.column_config.TextColumn("Category"),
    "previous": st.column_config.NumberColumn("Week before", format="$%,.0f"),
    "last": st.column_config.NumberColumn("Last week", format="$%,.0f"),
    "change": st.column_config.NumberColumn("Change", format="$%,.0f"),
    "change_pct": st.column_config.NumberColumn("Change %", format="percent"),
    "item": st.column_config.TextColumn("Item"),
    "dc": st.column_config.TextColumn("DC"),
    "on_hand": st.column_config.NumberColumn("On hand", format="localized"),
    "on_order": st.column_config.NumberColumn("On order", format="localized"),
    "weekly_forecast": st.column_config.NumberColumn(
        "Weekly forecast", format="localized"
    ),
    "days_of_cover": st.column_config.NumberColumn("Days of stock", format="%d days"),
    "order_qty": st.column_config.NumberColumn("Order qty", format="localized"),
    "value": st.column_config.NumberColumn("Value", format="$%,.0f"),
    "unit_cost": st.column_config.NumberColumn("Unit cost", format="dollar"),
    "case_pack": st.column_config.NumberColumn("Case pack"),
    "supplier": st.column_config.TextColumn("Supplier"),
    "confidence": st.column_config.ProgressColumn(
        "Confidence", format="percent", min_value=0, max_value=1, width="small"
    ),
    "po": st.column_config.TextColumn("PO"),
    "column": st.column_config.TextColumn("Column"),
    "type": st.column_config.TextColumn("Type"),
    "missing": st.column_config.ProgressColumn(
        "Missing", format="percent", min_value=0, max_value=1, width="small"
    ),
    "distinct": st.column_config.NumberColumn("Distinct", format="localized"),
    "example": st.column_config.TextColumn("Example"),
}


# Messages -------------------------------------------------------------------


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def conversation(text: str) -> list[dict[str, Any]]:
    """A finished exchange for a request, as it's kept in history."""
    return [
        {"role": "user", "id": new_id(), "text": text, "attachments": []},
        {"role": "assistant", "id": new_id(), "reply": agent.reply(text)},
    ]


def chats() -> dict[str, list[dict[str, Any]]]:
    """Every conversation in the session by ID, least recently active first.

    A new session starts with a few earlier chats, so the sidebar has
    something to show.
    """
    if "chats" not in st.session_state:
        st.session_state.chats = {
            new_id(): conversation(text) for text in agent.EARLIER_CHATS
        }
    return st.session_state.chats


def chat_id() -> str:
    """The ID of the open conversation."""
    return st.session_state.setdefault("chat_id", new_id())


def messages() -> list[dict[str, Any]]:
    """The open conversation."""
    return chats().setdefault(chat_id(), [])


def title(history: list[dict[str, Any]]) -> str:
    return next(
        (m["reply"].title for m in history if "reply" in m), history[0]["text"][:48]
    )


def find(message_id: str) -> dict[str, Any]:
    return next(m for m in messages() if m["id"] == message_id)


def pace() -> float:
    if "AGENT_APP_PACE" in os.environ:
        return float(os.environ["AGENT_APP_PACE"])
    return PACES[st.session_state.get("pace", "Natural")]


def pause(seconds: float) -> None:
    if pace():
        time.sleep(seconds * pace())


def words(text: str) -> Iterator[str]:
    """The answer, a word at a time, the way a model streams it."""
    for token in re.findall(r"\s*\S+", text):
        pause(0.04)
        yield token


def render_user(message: dict[str, Any]) -> None:
    with st.chat_message("user"):
        attachments: list[Attachment] = message.get("attachments", [])
        images = [a for a in attachments if a.is_image]
        others = [a for a in attachments if not a.is_image]
        if images:
            with st.container(horizontal=True):
                for image in images:
                    st.image(image.data, width=220, caption=image.name)
        if others:
            with st.container(horizontal=True, gap="small"):
                for file in others:
                    st.badge(
                        f"{file.name} · {file.size_label}",
                        icon=":material/attach_file:",
                        color="gray",
                    )
        if message["text"]:
            st.markdown(message["text"])


def render_assistant(message: dict[str, Any]) -> None:
    with st.chat_message("assistant", avatar=AVATAR):
        if "note" in message:
            st.markdown(message["note"])
            return
        reply: agent.Reply = message["reply"]
        steps(reply, live=False)
        st.markdown(reply.answer)
        result(reply, message["id"])
        actions(reply, message["id"])


def followups(slot: Any, message: dict[str, Any]) -> None:
    """The latest reply's follow-ups, in one row above the chat input.

    The pills sit in a container inside ``slot``, an ``st.bottom.empty()``. On
    a run that doesn't call this, such as while a new reply streams, the slot
    stays empty, which removes the pills right away. Pills placed directly in
    the slot would stay on screen until the reply finishes.
    """
    with slot.container():
        st.pills(
            "Follow up",
            list(message["reply"].followups),
            label_visibility="collapsed",
            wrap=False,
            key=f"followup_{message['id']}",
        )


def respond(text: str, attachments: list[Attachment]) -> dict[str, Any]:
    """Run the agent for a request and show its work as it happens."""
    message_id = new_id()
    with st.chat_message("assistant", avatar=AVATAR):
        reply = agent.reply(text, attachments)
        steps(reply, live=True)
        st.write_stream(words(reply.answer), cursor=CURSOR)
        result(reply, message_id)
        actions(reply, message_id)
    return {"role": "assistant", "id": message_id, "reply": reply}


def stopped(retry: Any) -> None:
    """The reply to a request whose run someone stopped."""
    with st.chat_message("assistant", avatar=AVATAR):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption("You stopped this response.")
            st.button(
                "Try again", icon=":material/refresh:", type="tertiary", on_click=retry
            )


# The agent's steps ----------------------------------------------------------


def steps(reply: agent.Reply, *, live: bool) -> None:
    """The agent's work as a compact "Thought for N seconds" toggle over a step timeline."""
    if not reply.steps:
        return
    seconds = reply.thinking_seconds
    done = f"Thought for {seconds} second{'s' if seconds != 1 else ''}"
    if not live:
        with st.status(done, type="compact", state="complete"):
            for step in reply.steps:
                with st.status(step.label, type="step", state="complete"):
                    step_details(step)
        return

    show = st.session_state.get("show_steps", True)
    with st.status(":shimmer[Thinking]", type="compact", expanded=show) as thinking:
        for step in reply.steps:
            with st.status(
                f":shimmer[{step.running}]", type="step", expanded=True
            ) as status:
                pause(step.seconds)
                step_details(step)
                status.update(label=step.label, state="complete")
        thinking.update(label=done, state="complete", expanded=False)


def step_details(step: agent.Step) -> None:
    if step.detail:
        st.markdown(step.detail)
    if step.code:
        st.code(step.code, language=step.language, wrap_lines=True)
    if step.table is not None:
        st.dataframe(step.table, hide_index=True, column_config=COLUMNS)


# Results in the message -----------------------------------------------------


def result(reply: agent.Reply, message_id: str) -> None:
    artifact = reply.artifact
    if reply.kind == "revenue":
        revenue_metrics(artifact)
        with st.container(border=True):
            st.markdown("**Revenue bridge**")
            st.caption(
                f"West, week of {data.week_label(artifact.week)} against the week before"
            )
            st.echarts_chart(
                charts.revenue_bridge(artifact),
                height=280,
                alt="Waterfall from the week before to last week: outerwear online fell "
                "the most, wholesale camping fell, and footwear rose",
            )
    elif reply.kind == "pricing":
        pricing_metrics(artifact)
        with st.container(border=True):
            st.markdown("**Gross margin over the next eight weeks**")
            st.caption(
                "Boxes hold the middle half of 2,000 simulated futures per price"
            )
            st.echarts_chart(
                charts.margin_range(artifact),
                height=260,
                alt="Gross margin ranges for three prices of the Summit down jacket",
            )
    elif reply.kind == "restock":
        restock_summary(artifact, message_id)
    elif reply.kind == "summary":
        kpi_grid(artifact.kpis)
    elif reply.kind == "file":
        file_result(artifact)


def revenue_metrics(change: data.RevenueChange) -> None:
    totals = data.weekly_revenue()
    weekly = (
        totals[totals["region"] == change.region]
        .groupby("week")[["net_revenue", "orders"]]
        .sum()
    )
    grid = st.grid(3, gap="small")
    grid.metric(
        "Net revenue",
        money(change.revenue),
        f"{change.change_pct:+.1%}",
        chart_data=weekly["net_revenue"],
        chart_type="area",
        delta_description="vs. week before",
        border=True,
    )
    grid.metric(
        "Orders",
        f"{change.orders:,.0f}",
        f"{change.orders / change.previous_orders - 1:+.1%}",
        chart_data=weekly["orders"],
        chart_type="area",
        delta_description="vs. week before",
        border=True,
    )
    grid.metric(
        "Average order",
        f"${change.average_order:,.0f}",
        f"{change.average_order / change.previous_average_order - 1:+.1%}",
        chart_data=weekly["net_revenue"] / weekly["orders"],
        chart_type="area",
        delta_description="vs. week before",
        border=True,
    )


def price_name(outcome: pricing.Outcome) -> str:
    return f"${outcome.price:.0f}" + (
        " today" if outcome.label == "Current price" else f" ({outcome.label})"
    )


def pricing_metrics(outcomes: list[pricing.Outcome]) -> None:
    current = next(o for o in outcomes if o.label == "Current price")
    grid = st.grid(3, gap="small")
    for outcome in outcomes:
        gap = outcome.p(50) - current.p(50)
        grid.metric(
            price_name(outcome),
            money(outcome.p(50)),
            None
            if outcome is current
            else ("+" if gap >= 0 else "-") + money(abs(gap)),
            delta_description=None if outcome is current else "vs. today",
            help=f"Median gross margin over 8 weeks. P10 {money(outcome.p(10))}, "
            f"P90 {money(outcome.p(90))}.",
            border=True,
        )


def restock_summary(proposals: agent.Proposals, message_id: str) -> None:
    table = proposals.table
    view = table[["item", "dc", "days_of_cover", "order_qty", "value", "confidence"]]
    st.dataframe(view, hide_index=True, column_config=COLUMNS)
    with st.container(horizontal=True, vertical_alignment="center"):
        if proposals.submitted:
            st.badge(
                f"{len(proposals.approved)} approved by you",
                icon=":material/task_alt:",
                color="green",
            )
        else:
            if st.button(
                "Review and approve",
                icon=":material/fact_check:",
                type="primary",
                key=f"review_{message_id}",
            ):
                canvas(message_id)
            st.caption("Nothing is ordered until you approve.")


def kpi_grid(kpis: list[data.Kpi]) -> None:
    grid = st.grid(2, gap="small")
    for kpi in kpis:
        if kpi.kind == "percent":
            value, delta = (
                f"{kpi.value:.1%}",
                f"{(kpi.value - kpi.previous) * 100:+.1f} pts",
            )
        else:
            value = money(kpi.value) if kpi.kind == "money" else f"{kpi.value:,.0f}"
            if kpi.label == "Average order":
                value = f"${kpi.value:,.2f}"
            delta = f"{kpi.value / kpi.previous - 1:+.1%}"
        grid.metric(
            kpi.label,
            value,
            delta,
            chart_data=kpi.history,
            chart_type="area",
            delta_description="vs. week before",
            border=True,
        )


def file_result(profile: Profile) -> None:
    if profile.series is not None:
        with st.container(border=True):
            st.markdown(f"**{profile.series.value}**")
            st.caption(f"By {profile.series.date}, from {profile.name}")
            st.echarts_chart(
                charts.file_series(profile.series),
                height=240,
                alt=f"{profile.series.value} over time, from {profile.name}",
            )
    elif profile.frame is not None:
        st.dataframe(profile.frame.head(8), hide_index=True)


# Actions and follow-ups -----------------------------------------------------


def saved_feedback(message_id: str) -> None:
    score = st.session_state.get(f"feedback_{message_id}")
    if score is not None:
        st.toast(
            "Thanks, that helps the team improve the analyst.",
            icon=":material/thumb_up:" if score else ":material/thumb_down:",
        )


def actions(reply: agent.Reply, message_id: str) -> None:
    if reply.kind == "help":
        return
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.feedback(
            "thumbs",
            key=f"feedback_{message_id}",
            on_change=saved_feedback,
            args=(message_id,),
        )
        if reply.kind in CANVAS_KINDS and not (
            reply.kind == "file" and reply.artifact.kind != "table"
        ):
            if st.button(
                "Open in canvas",
                icon=":material/right_panel_open:",
                type="tertiary",
                key=f"canvas_{message_id}",
            ):
                canvas(message_id)


# The canvas -----------------------------------------------------------------


@st.dialog("Canvas", position="right", width=860, icon=":material/right_panel_open:")
def canvas(message_id: str) -> None:
    """The full analysis behind a reply, in a resizable side drawer."""
    message = find(message_id)
    reply: agent.Reply = message["reply"]
    {
        "revenue": revenue_canvas,
        "pricing": pricing_canvas,
        "restock": restock_canvas,
        "summary": summary_canvas,
        "file": file_canvas,
    }[reply.kind](reply, message_id)


def revenue_canvas(reply: agent.Reply, message_id: str) -> None:
    change: data.RevenueChange = reply.artifact
    st.title(f"West revenue, week of {data.week_label(change.week)}", anchor=False)
    st.caption(
        "Net revenue, certified definition · from `cairn.sales.revenue` · "
        f"{pct(change.change_pct)} against the week before"
    )
    revenue_metrics(change)
    bridge, trend, cells, query = st.tabs(["Bridge", "Trend", "By category", "Query"])
    with bridge:
        st.echarts_chart(
            charts.revenue_bridge(change),
            height=340,
            alt="Waterfall from the week before to last week by driver",
        )
        for driver in change.drivers:
            st.markdown(
                f"**{driver.label}** · {money(driver.change)} · {driver.detail}"
            )
    with trend:
        st.echarts_chart(
            charts.revenue_trend(change),
            height=320,
            alt="Weekly net revenue in the West by channel for 12 weeks",
        )
        st.caption(
            "Online dips in the last week; stores and wholesale hold their level."
        )
    with cells:
        st.dataframe(change.by_cell, hide_index=True, column_config=COLUMNS)
    with query:
        st.code(agent.REVENUE_SQL, language="sql")
        st.markdown(
            "**Net revenue:** gross sales minus returns and discounts, excluding tax. "
            "**Orders:** completed orders, net of cancellations. Both come from the "
            "semantic view the revenue dashboard uses, so the numbers match."
        )


def pricing_canvas(reply: agent.Reply, message_id: str) -> None:
    outcomes: list[pricing.Outcome] = reply.artifact
    st.title(f"{data.JACKET.name}: three prices", anchor=False)
    st.caption(
        f"{pricing.RUNS:,} simulated futures per price · next {pricing.WEEKS} weeks · "
        "gross margin after unit cost"
    )
    pricing_metrics(outcomes)
    outcomes_tab, weekly_tab, assumptions_tab, method_tab = st.tabs(
        ["Outcomes", "Weekly units", "Assumptions", "Method"]
    )
    with outcomes_tab:
        st.echarts_chart(
            charts.margin_range(outcomes),
            height=300,
            alt="Gross margin ranges per price",
        )
        table = pd.DataFrame(
            {
                "Price": [price_name(o) for o in outcomes],
                "Units sold": [o.units_sold for o in outcomes],
                "Unmet demand": [o.lost_units for o in outcomes],
                "Margin P10": [o.p(10) for o in outcomes],
                "Margin P50": [o.p(50) for o in outcomes],
                "Margin P90": [o.p(90) for o in outcomes],
            }
        )
        st.dataframe(
            table,
            hide_index=True,
            column_config={
                "Units sold": st.column_config.NumberColumn(format="localized"),
                "Unmet demand": st.column_config.NumberColumn(format="localized"),
                "Margin P10": st.column_config.NumberColumn(format="$%,.0f"),
                "Margin P50": st.column_config.NumberColumn(format="$%,.0f"),
                "Margin P90": st.column_config.NumberColumn(format="$%,.0f"),
            },
        )
    with weekly_tab:
        st.echarts_chart(
            charts.weekly_units(outcomes),
            height=320,
            alt="Median weekly units per price against supply",
        )
        st.caption(
            "Week 1 is capped by supply at every price until the Reno restock lands."
        )
    with assumptions_tab:
        jacket = data.JACKET
        st.markdown(
            f"- **Demand:** {jacket.weekly_demand:.0f} units a week at ${jacket.price:.0f}\n"
            f"- **Price elasticity:** {jacket.elasticity} ± {jacket.elasticity_sd}, "
            "drawn once per future\n"
            "- **Weekly noise:** lognormal, σ 0.16\n"
            f"- **Unit cost:** ${jacket.unit_cost:.0f}\n"
            f"- **Supply:** {data.JACKET_SUPPLY[0]} units in week 1, then "
            f"{data.JACKET_SUPPLY[1]} a week"
        )
    with method_tab:
        st.caption("The function the agent ran, unchanged:")
        st.code(inspect.getsource(pricing.simulate), language="python")


def restock_canvas(reply: agent.Reply, message_id: str) -> None:
    proposals: agent.Proposals = reply.artifact
    st.title("Draft purchase orders", anchor=False)
    st.caption(
        "Six weeks of demand per item, in whole cases. Nothing is ordered until you "
        "approve it."
    )
    if proposals.submitted:
        st.success(
            f"You approved {len(proposals.approved)} orders. They're in the purchasing queue.",
            icon=":material/task_alt:",
        )
        table = proposals.table.assign(
            status=proposals.table["po"].map(
                lambda po: "Approved" if po in proposals.approved else "Draft"
            )
        )
        st.dataframe(
            table[["status", "po", "item", "dc", "order_qty", "value"]],
            hide_index=True,
            column_config={**COLUMNS, "status": st.column_config.TextColumn("Status")},
        )
        return

    table = proposals.table.assign(
        supplier=proposals.table.apply(
            lambda row: (
                f"{row['supplier']} (new)" if row["new_supplier"] else row["supplier"]
            ),
            axis=1,
        )
    )
    columns = [
        "approve",
        "item",
        "dc",
        "days_of_cover",
        "order_qty",
        "unit_cost",
        "supplier",
        "confidence",
    ]
    edited = st.data_editor(
        table[columns],
        hide_index=True,
        disabled=[c for c in columns if c not in ("approve", "order_qty")],
        column_config={
            **COLUMNS,
            "approve": st.column_config.CheckboxColumn("Approve", width=100),
            "order_qty": st.column_config.NumberColumn(
                "Order qty",
                min_value=0,
                step=1,
                format="localized",
                help="Whole cases only",
            ),
        },
        key=f"orders_{message_id}",
    )
    edited = edited.assign(
        value=edited["order_qty"] * edited["unit_cost"],
        case_pack=proposals.table["case_pack"].values,
    )
    chosen = edited[edited["approve"]]
    with st.container(horizontal=True, gap="small"):
        st.metric("Selected", f"{len(chosen)} of {len(edited)}", border=True)
        st.metric("Order value", money(chosen["value"].sum()), border=True)
        st.metric(
            "Largest order",
            money(chosen["value"].max() if len(chosen) else 0),
            border=True,
            help=f"Each order must stay under {money(agent.ORDER_CAP)}.",
        )

    problem = agent.validate_orders(edited)
    if st.button(
        f"Approve {len(chosen)} order{'s' if len(chosen) != 1 else ''}",
        icon=":material/check:",
        type="primary",
        disabled=chosen.empty,
        key=f"approve_{message_id}",
    ):
        if problem:
            st.error(problem, icon=":material/error:")
        else:
            proposals.table = proposals.table.assign(
                order_qty=edited["order_qty"].values
            ).assign(value=lambda t: t["order_qty"] * t["unit_cost"])
            proposals.submitted = True
            proposals.approved = list(proposals.table.loc[chosen.index, "po"])
            drafts = len(edited) - len(chosen)
            messages().append(
                {
                    "role": "assistant",
                    "id": new_id(),
                    "note": f":green-badge[:material/task_alt: Approved] You approved "
                    f"**{len(chosen)} purchase orders worth {money(chosen['value'].sum())}**. "
                    "They're in the purchasing queue"
                    + (
                        ", and the other one stays as a draft."
                        if drafts == 1
                        else f", and the other {drafts} stay as drafts."
                        if drafts
                        else "."
                    ),
                }
            )
            st.rerun()


def summary_canvas(reply: agent.Reply, message_id: str) -> None:
    summary: agent.Summary = reply.artifact
    st.title(f"Weekly update, week of {summary.week}", anchor=False)
    st.caption("Drafted from the certified KPIs. Edit it before you send it.")
    kpi_grid(summary.kpis)
    with st.container(border=True):
        st.markdown(reply.answer)
    st.download_button(
        "Download as Markdown",
        summary.document,
        file_name=f"weekly-update-{summary.week.lower().replace(' ', '-')}.md",
        mime="text/markdown",
        icon=":material/download:",
    )


def file_canvas(reply: agent.Reply, message_id: str) -> None:
    profile: Profile = reply.artifact
    st.title(profile.name, anchor=False)
    st.caption(profile.summary)
    if profile.frame is None:
        return
    tabs = ["Rows", "Columns"] + (["Chart"] if profile.series is not None else [])
    rows, columns, *chart = st.tabs(tabs)
    with rows:
        st.dataframe(profile.frame, hide_index=True, height=420)
    with columns:
        st.dataframe(profile.columns, hide_index=True, column_config=COLUMNS)
    if chart and profile.series is not None:
        with chart[0]:
            st.echarts_chart(
                charts.file_series(profile.series),
                height=320,
                alt=f"{profile.series.value} over time",
            )


def transcript() -> str:
    lines = []
    for message in messages():
        if message["role"] == "user":
            lines.append(f"**You:** {message['text']}")
        elif "note" in message:
            lines.append(
                f"**Cairn Analyst:** {re.sub(r':[a-z-]+\[[^\]]*\]', '', message['note']).strip()}"
            )
        else:
            lines.append(f"**Cairn Analyst:** {message['reply'].answer}")
    return "\n\n".join(lines) + "\n"
