"""Headless checks for Cairn Analyst. Run with ``pytest tests`` from the app folder.

``AGENT_APP_PACE=0`` skips the demo's pauses, so every reply is instant.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_DIR = Path(__file__).parent.parent
APP = str(APP_DIR / "streamlit_app.py")
sys.path.insert(0, str(APP_DIR))
os.environ["AGENT_APP_PACE"] = "0"

from utils import agent, files  # noqa: E402


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(APP, default_timeout=30).run()


def ask(at: AppTest, text: str) -> AppTest:
    at.chat_input[0].set_value(text).run()
    assert not at.exception
    return at


def answers(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_welcome_renders(at: AppTest) -> None:
    assert not at.exception
    assert at.title[0].value == "What should we look into today?"


def test_revenue_question_explains_the_drop(at: AppTest) -> None:
    ask(at, "Why did net revenue in the West fall last week?")
    assert "Net revenue in the West fell" in answers(at)
    assert {"Net revenue", "Orders", "Average order"} <= {m.label for m in at.metric}


def test_pricing_compares_three_prices(at: AppTest) -> None:
    ask(at, "Compare three price scenarios for the Summit down jacket")
    labels = [m.label for m in at.metric]
    assert labels == ["$224 (-10%)", "$249 today", "$274 (+10%)"]


def test_unknown_requests_get_help(at: AppTest) -> None:
    ask(at, "What's the weather in Reno?")
    assert "can't answer that one yet" in answers(at)


def test_routing() -> None:
    assert agent.route("Draft restock orders", []) == "restock"
    assert agent.route("Summarize the week", []) == "summary"
    assert agent.route("What if we cut the price?", []) == "pricing"
    assert agent.route("Why did sales drop?", []) == "revenue"


def test_orders_need_whole_cases_and_a_selection() -> None:
    table = agent.proposals()
    assert agent.validate_orders(table) is None
    assert (
        agent.validate_orders(table.assign(approve=False))
        == "Select at least one order to approve."
    )
    odd = table.copy()
    odd.loc[0, "order_qty"] += 1
    assert agent.validate_orders(odd).startswith("Order ")


def test_csv_profile_finds_the_series() -> None:
    csv = (
        b"date,units,revenue\n2026-01-01,10,120.5\n2026-01-02,12,140\n2026-01-03,,98\n"
    )
    profile = files.profile(files.Attachment("sales.csv", "text/csv", len(csv), csv))
    assert profile.kind == "table"
    assert profile.series is not None and profile.series.value == "revenue"
    assert "3 rows and 3 columns" in files.describe(profile, "")
