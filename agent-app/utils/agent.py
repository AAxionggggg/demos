"""The demo's agent: scripted analyses that compute real answers from synthetic data.

No model is called. ``reply`` picks one of the scripted analyses for the
request and returns a ``Reply``: the steps the agent took, the answer to
stream, and an artifact for the message and the canvas. The numbers come from
``utils.data`` and ``utils.pricing``, so they are consistent everywhere.

To use a real model, keep the ``Reply`` shape and build it from your model's
or agent framework's events: tool calls become ``Step`` objects, and the
answer is the model's streamed text.
"""

from __future__ import annotations

import inspect
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from utils import data, files, pricing
from utils.format import money, pct, signed_money

Kind = Literal["revenue", "pricing", "restock", "summary", "file", "help"]


@dataclass
class Step:
    """One tool call or stage of work, shown as a step in the timeline."""

    label: str  # When it's done, such as "Queried weekly revenue"
    running: str  # While it runs, such as "Querying weekly revenue"
    seconds: float  # How long the step takes in the demo's story
    detail: str = ""  # Markdown
    code: str | None = None
    language: str = "sql"
    table: pd.DataFrame | None = None


@dataclass
class Reply:
    kind: Kind
    title: str  # A short title for the conversation
    answer: str  # Markdown, streamed into the message
    steps: list[Step] = field(default_factory=list)
    artifact: Any = None
    followups: list[str] = field(default_factory=list)

    @property
    def thinking_seconds(self) -> int:
        return max(1, round(sum(step.seconds for step in self.steps)))


SUGGESTIONS = {
    ":material/trending_down: Why West revenue fell": "Why did net revenue in the West fall last week?",
    ":material/sell: Compare prices": "Compare three price scenarios for the Summit down jacket",
    ":material/inventory: Draft restock orders": "Draft purchase orders for items at risk of stocking out",
    ":material/summarize: Summarize the week": "Summarize last week for the leadership update",
}

ROUTES: list[tuple[Kind, str]] = [
    ("pricing", r"price|pricing|scenario|elastic|discount|markdown|simulat"),
    ("restock", r"restock|reorder|replenish|purchase|stock|inventory|\border"),
    ("summary", r"summar|leadership|update|brief|recap|report|kpi"),
    ("revenue", r"revenue|sales|fell|fall|drop|declin|down|why|west"),
]


def route(text: str, attachments: list[files.Attachment]) -> Kind:
    if attachments:
        return "file"
    lowered = text.lower()
    for kind, pattern in ROUTES:
        if re.search(pattern, lowered):
            return kind
    return "help"


def reply(text: str, attachments: list[files.Attachment] | None = None) -> Reply:
    """The agent's reply to a request, with the steps it took to get there."""
    attachments = attachments or []
    kind = route(text, attachments)
    if kind == "file":
        return file_reply(text, attachments)
    return {
        "revenue": revenue_reply,
        "pricing": pricing_reply,
        "restock": restock_reply,
        "summary": summary_reply,
        "help": help_reply,
    }[kind]()


def revenue_reply() -> Reply:
    change = data.revenue_change("West")
    stockout, slip, launch, other = change.drivers
    week = data.week_label(change.week)
    movers = change.by_cell.head(4)[
        ["channel", "category", "previous", "last", "change"]
    ]

    answer = f"""\
**Net revenue in the West fell {pct(change.change_pct, signed=False)} last week, to \
{money(change.revenue)}**, {money(-change.change)} less than the week before. Two things \
explain most of it:

1. **The {data.STOCKOUT_ITEM} sold out online.** The {data.STOCKOUT_DC} distribution \
center ran out on Tuesday, and outerwear revenue online fell {money(-stockout.change)}. \
Product page views held steady, so these are lost sales, not lost interest.
2. **A wholesale order slipped a week.** {data.WHOLESALE_ACCOUNT}' camping order \
({data.SLIPPED_PO}, {money(data.WHOLESALE_SLIP)}) moved to this week, so wholesale \
camping fell {money(-slip.change)}. That's timing, not lost revenue.

The {data.LAUNCH_ITEM} launch offset part of it: footwear rose {money(launch.change)}. \
Everything else moved {signed_money(other.change)}, within its normal weekly range.

Restocking the jacket is the fastest fix. I can draft the purchase orders, or compare \
price scenarios for when it's back."""

    steps = [
        Step(
            "Read the metric definition",
            "Reading the metric definition",
            0.9,
            "**Net revenue** is gross sales minus returns and discounts, excluding tax. "
            "It's the certified definition the revenue dashboard uses.",
        ),
        Step(
            "Queried weekly revenue for the West",
            "Querying weekly revenue for the West",
            2.1,
            f"12 weeks · 3 channels · 5 categories · {len(change.by_cell) * 12} rows",
            code=REVENUE_SQL,
        ),
        Step(
            "Broke the change down by channel and category",
            "Breaking the change down",
            1.6,
            f"Week of {week} against the week before. The biggest moves:",
            table=movers,
        ),
        Step(
            "Checked inventory and the order log",
            "Checking inventory and the order log",
            1.4,
            f"- {data.STOCKOUT_ITEM}: 0 units at {data.STOCKOUT_DC} since Tuesday, page "
            f"views flat\n- {data.SLIPPED_PO} from {data.WHOLESALE_ACCOUNT}: ship date "
            "moved by one week",
        ),
    ]
    return Reply(
        "revenue",
        "Why West revenue fell",
        answer,
        steps,
        artifact=change,
        followups=[
            "Draft purchase orders to restock the Summit down jacket",
            "Compare three price scenarios for the Summit down jacket",
            "Summarize last week for the leadership update",
        ],
    )


def pricing_reply() -> Reply:
    started = time.perf_counter()
    outcomes = pricing.compare()
    elapsed = time.perf_counter() - started
    cut, current, raised = outcomes
    best = max(outcomes, key=lambda o: o.p(50))

    def describe(o: pricing.Outcome) -> str:
        price = f"**${o.price:.0f}** ({'current' if o is current else o.label})"
        if o is cut:
            return (
                f"{price} would sell the most, about {o.units_sold:,.0f} jackets, but the "
                f"Reno restock only lands next week, so about {o.lost_units:,.0f} jackets "
                f"of demand go unmet. Median margin {money(o.p(50))}."
            )
        if o is current:
            return (
                f"{price} sells about {o.units_sold:,.0f} jackets for a median margin of "
                f"{money(o.p(50))}."
            )
        text = (
            f"{price} sells about {o.units_sold:,.0f} jackets for a median margin of "
            f"{money(o.p(50))}."
        )
        if o.p(10) > current.p(50):
            text += f" Even its weak case (P10, {money(o.p(10))}) beats today's median."
        return text

    if best is current:
        lead = (
            f"**Keep the price at ${current.price:.0f}.** It has the highest median gross "
            f"margin over the next eight weeks, {money(current.p(50))}."
        )
        trade_off = ""
    else:
        gap = best.p(50) - current.p(50)
        verb = "Raising" if best.price > current.price else "Cutting"
        lead = (
            f"**{verb} the price to ${best.price:.0f} earns the most: a median gross "
            f"margin of {money(best.p(50))} over the next eight weeks**, "
            f"{money(gap)} more than today's ${current.price:.0f}."
        )
        fewer = current.units_sold - best.units_sold
        trade_off = (
            (
                f"\n\nThe catch: it sells about {fewer:,.0f} fewer jackets at the start "
                f"of peak season. If keeping customers matters more than {money(gap)} of "
                f"margin, hold at ${current.price:.0f}."
            )
            if fewer > 0
            else ""
        )

    answer = (
        lead
        + "\n\n"
        + "\n".join(f"- {describe(o)}" for o in (raised, current, cut))
        + trade_off
        + "\n\nAll three use the same simulated futures, so the differences come from "
        "the price alone."
    )
    steps = [
        Step(
            "Loaded the demand model",
            "Loading the demand model",
            1.1,
            f"Price elasticity {data.JACKET.elasticity} ± {data.JACKET.elasticity_sd}, "
            f"fit on two seasons of weekly sales. {data.JACKET.weekly_demand:.0f} units a "
            f"week at ${data.JACKET.price:.0f}.",
        ),
        Step(
            "Checked supply",
            "Checking supply",
            1.0,
            f"{data.JACKET_SUPPLY[0]} units available this week, then "
            f"{data.JACKET_SUPPLY[1]} a week once the Reno restock lands.",
        ),
        Step(
            f"Simulated {pricing.RUNS:,} futures for each price",
            f"Simulating {pricing.RUNS:,} futures for each price",
            2.4,
            f"{pricing.RUNS * len(outcomes):,} runs of {pricing.WEEKS} weeks in "
            f"{elapsed * 1000:.0f} ms, with the same random futures for every price.",
            code=inspect.getsource(pricing.simulate),
            language="python",
        ),
        Step(
            "Compared margin and risk",
            "Comparing margin and risk",
            0.8,
            " · ".join(f"${o.price:.0f}: P50 {money(o.p(50))}" for o in outcomes),
        ),
    ]
    return Reply(
        "pricing",
        "Summit jacket price scenarios",
        answer,
        steps,
        artifact=outcomes,
        followups=[
            "Draft purchase orders to restock the Summit down jacket",
            "Why did net revenue in the West fall last week?",
        ],
    )


@dataclass
class Proposals:
    """Draft purchase orders and what the person reviewing them decided."""

    table: pd.DataFrame
    submitted: bool = False
    approved: list[str] = field(default_factory=list)


def proposals() -> pd.DataFrame:
    stock = data.stock_positions()
    need = 6 * stock["weekly_forecast"] - stock["on_hand"] - stock["on_order"]
    cases = (need.clip(lower=0) / stock["case_pack"]).map(math.ceil)
    stock["order_qty"] = cases * stock["case_pack"]
    stock["value"] = stock["order_qty"] * stock["unit_cost"]
    stock["days_of_cover"] = (stock["on_hand"] / (stock["weekly_forecast"] / 7)).round()
    stock["po"] = [f"PO-{49100 + i}" for i in range(len(stock))]
    stock["approve"] = ~stock["new_supplier"] & (stock["confidence"] >= 0.8)
    return stock.sort_values("days_of_cover").reset_index(drop=True)


def restock_reply() -> Reply:
    table = proposals()
    urgent = table.iloc[0]
    flagged = table[table["new_supplier"]]
    arrival = urgent["lead_days"]
    answer = f"""\
**I drafted {len(table)} purchase orders worth {money(table["value"].sum())} to cover the \
next six weeks.** Nothing is ordered until you approve them.

The **{urgent["item"]} at {urgent["dc"]}** is the most urgent: it's out of stock, and an \
order approved today arrives in {arrival} days. I sized it at \
{urgent["order_qty"]:,} units ({urgent["order_qty"] // urgent["case_pack"]} cases), six \
weeks of demand."""
    if not flagged.empty:
        item = flagged.iloc[0]
        answer += (
            f"\n\nThe **{item['item']}** comes from {item['supplier']}, a new supplier, "
            "so I left it unchecked for you to review."
        )
    answer += "\n\nCheck the quantities, then approve the orders you want to place."

    steps = [
        Step(
            "Found items at risk of stocking out",
            "Looking for items at risk of stocking out",
            1.3,
            f"{len(table)} of 412 item and distribution center pairs have under three "
            "weeks of stock.",
        ),
        Step(
            "Forecast six weeks of demand",
            "Forecasting six weeks of demand",
            1.5,
            "Weekly forecast from the demand model, net of stock on hand and on order.",
            table=table[["item", "dc", "on_hand", "on_order", "weekly_forecast"]],
        ),
        Step(
            "Sized each order to whole cases",
            "Sizing each order",
            0.9,
            "Rounded up to the supplier's case pack, so every order ships as full cases.",
        ),
        Step(
            "Checked guardrails",
            "Checking guardrails",
            0.8,
            guardrail_check(table, flagged),
        ),
    ]
    return Reply(
        "restock",
        "Restock orders",
        answer,
        steps,
        artifact=Proposals(table),
        followups=["Summarize last week for the leadership update"],
    )


ORDER_CAP = 300_000


def guardrail_check(table: pd.DataFrame, flagged: pd.DataFrame) -> str:
    over = table[table["value"] > ORDER_CAP]
    cap = (
        f"Every order is under the {money(ORDER_CAP)} cap."
        if over.empty
        else f"{len(over)} {'order is' if len(over) == 1 else 'orders are'} over the "
        f"{money(ORDER_CAP)} cap."
    )
    suppliers = (
        f" {len(flagged)} {'order comes' if len(flagged) == 1 else 'orders come'} from a "
        "new supplier, so a person approves it."
        if len(flagged)
        else " No new suppliers."
    )
    return cap + suppliers


def validate_orders(table: pd.DataFrame) -> str | None:
    """A problem with the orders people chose to approve, or None."""
    chosen = table[table["approve"]]
    if chosen.empty:
        return "Select at least one order to approve."
    for _, row in chosen.iterrows():
        if row["order_qty"] <= 0:
            return f"Set a quantity for {row['item']} at {row['dc']}."
        if row["order_qty"] % row["case_pack"]:
            return f"Order {row['item']} in whole cases of {row['case_pack']}."
        if row["order_qty"] * row["unit_cost"] > ORDER_CAP:
            return f"{row['item']} at {row['dc']} is over the {money(ORDER_CAP)} order cap."
    return None


@dataclass
class Summary:
    kpis: list[data.Kpi]
    document: str
    week: str


def summary_reply() -> Reply:
    kpis = data.company_kpis()
    revenue, orders, average_order, margin = kpis
    regions = (
        data.weekly_revenue().groupby(["week", "region"])["net_revenue"].sum().unstack()
    )
    change = regions.iloc[-1] / regions.iloc[-2] - 1
    week = data.week_label(data.week_starts()[-1])
    restock = proposals()

    answer = f"""\
**Net revenue was {money(revenue.value)} last week, {pct(revenue.value / revenue.previous - 1)} \
against the week before and {pct(revenue.value / revenue.plan - 1)} against plan.** Orders \
moved {pct(orders.value / orders.previous - 1)}, and gross margin held at {margin.value:.1%}.

- **West ({pct(change["West"])}):** the {data.STOCKOUT_ITEM} sold out online, and \
{data.WHOLESALE_ACCOUNT}' order slipped a week. The {data.LAUNCH_ITEM} launch helped \
footwear.
- **Central ({pct(change["Central"])}) and East ({pct(change["East"])}):** in line with \
the season.

**Next steps:** approve the jacket restock ({money(restock["value"].sum())} across \
{len(restock)} orders), and expect the slipped wholesale order to land this week."""
    document = f"# Weekly update, week of {week}\n\n{answer}\n"
    steps = [
        Step(
            "Pulled the certified KPIs",
            "Pulling the certified KPIs",
            1.2,
            "Net revenue, orders, average order, and gross margin, from the revenue "
            "dashboard's definitions.",
        ),
        Step(
            "Compared them to last week and the plan",
            "Comparing to last week and the plan",
            1.0,
            " · ".join(
                f"{k.label} {pct(k.value / k.previous - 1)}" for k in (revenue, orders)
            ),
        ),
        Step(
            "Explained the biggest change",
            "Explaining the biggest change",
            1.6,
            "The West accounts for most of the change. Reused this week's analysis of "
            "its revenue.",
        ),
        Step(
            "Drafted the update",
            "Drafting the update",
            0.9,
            "Four sentences and two bullets.",
        ),
    ]
    return Reply(
        "summary",
        "Weekly leadership update",
        answer,
        steps,
        artifact=Summary(kpis, document, week),
        followups=["Why did net revenue in the West fall last week?"],
    )


def file_reply(text: str, attachments: list[files.Attachment]) -> Reply:
    profiles = [files.profile(attachment) for attachment in attachments]
    lead = profiles[0]
    steps = [
        Step(
            f"Read {p.name}",
            f"Reading {p.name}",
            0.8,
            p.summary,
            table=p.columns if p.columns is not None else None,
        )
        for p in profiles
    ]
    if lead.frame is not None and lead.series is not None:
        steps.append(
            Step(
                "Found a time series",
                "Looking for a time series",
                0.9,
                f"`{lead.series.value}` over `{lead.series.date}`, {lead.series.points} points.",
            )
        )
    answer = files.describe(lead, text)
    if len(profiles) > 1:
        answer += f"\n\nYou attached {len(profiles)} files. I profiled each one in the steps above."
    return Reply(
        "file",
        lead.name,
        answer,
        steps,
        artifact=lead,
        followups=list(SUGGESTIONS.values())[:2],
    )


def help_reply() -> Reply:
    answer = (
        "This demo plays back a few analyses of Cairn's sales, demand, and inventory "
        "data, so it can't answer that one yet. It doesn't call a model.\n\n"
        "Try one of the questions below, or attach a CSV, and I'll profile and chart it."
    )
    steps = [
        Step(
            "Matched the request to the demo's analyses",
            "Reading the request",
            0.6,
            "No scripted analysis matches. Real agents would plan their own tool calls here.",
        )
    ]
    return Reply(
        "help", "Getting started", answer, steps, followups=list(SUGGESTIONS.values())
    )


REVENUE_SQL = """\
select week, channel, category,
       sum(net_revenue) as net_revenue,
       sum(orders) as orders
from cairn.sales.revenue        -- semantic view
where region = 'West'
  and week >= dateadd(week, -12, current_date)
group by all"""
