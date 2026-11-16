"""Headless checks for Cairn Reorder desk. Run with ``pytest tests`` from the app folder.

Each test gets its own SQLite file, so the shared demo database is untouched.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Metric

APP_DIR = Path(__file__).parent.parent
APP = str(APP_DIR / "streamlit_app.py")
sys.path.insert(0, str(APP_DIR))

from utils import rules, seed, store  # noqa: E402


@pytest.fixture
def at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("REORDER_DESK_DB_DIR", str(tmp_path))
    st.cache_data.clear()
    st.cache_resource.clear()
    return AppTest.from_file(APP, default_timeout=30).run()


def metric(at: AppTest, label: str) -> Metric:
    return next(m for m in at.metric if m.label == label)


def test_queue_loads_todays_agent_run(at: AppTest) -> None:
    assert not at.exception
    assert int(metric(at, "Awaiting review").value) > 20
    assert metric(at, "Approved today").value == "$0"


def test_accepting_low_risk_writes_back(at: AppTest) -> None:
    waiting = int(metric(at, "Awaiting review").value)
    at.button(key="accept_low_risk").click().run()
    submit = at.button(key="submit")
    assert submit.label.startswith("Submit ")
    accepted = int(submit.label.split()[1])
    submit.click().run()
    assert not at.exception
    assert int(metric(at, "Awaiting review").value) == waiting - accepted
    assert metric(at, "Approved today").delta == f"{accepted} orders"


def test_guardrails_block_invalid_decisions() -> None:
    proposal = pd.Series(seed.proposals(date.today())[0])
    policies = pd.DataFrame(
        seed.DEFAULT_POLICIES,
        index=["auto_approve_limit", "order_cap", "max_change_pct", "min_confidence"],
    ).T
    agent_qty, pack = int(proposal["proposed_qty"]), int(proposal["case_pack"])

    def check(action: str, quantity: int, note: str = "") -> str | None:
        decision = store.Decision(str(proposal["id"]), action, quantity, note)
        return rules.validate(decision, proposal, policies)

    assert check("approve", agent_qty) is None
    assert check("approve", agent_qty + 1) == f"Order whole cases of {pack}"
    assert check("reject", 0) == "Add a note to reject"
    assert check("reject", 0, "Covered by a transfer.") is None
    doubled = agent_qty * 2
    if (
        doubled * proposal["unit_cost"]
        <= policies.loc[proposal["category"], "order_cap"]
    ):
        assert (check("approve", doubled) or "").startswith("Add a note")
        assert check("approve", doubled, "Promo next week.") is None


def test_activity_and_guardrails_render(at: AppTest) -> None:
    at.switch_page("app_pages/activity.py").run()
    assert not at.exception
    assert len(at.dataframe[0].value) > 100  # A month of decisions
    at.switch_page("app_pages/guardrails.py").run()
    assert not at.exception
    assert metric(at, "Over the order cap").value == "0"
