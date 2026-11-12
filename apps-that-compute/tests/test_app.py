"""Headless checks for Cairn Demand lab. Run with ``pytest tests`` from the app folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Metric

APP = str(Path(__file__).parent.parent / "streamlit_app.py")


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(APP, default_timeout=30).run()


def metric(at: AppTest, label: str) -> Metric:
    return next(m for m in at.metric if m.label == label)


def test_forecast_starts_on_plan(at: AppTest) -> None:
    assert not at.exception
    assert metric(at, "Units sold").delta == "On plan"
    assert [m.label for m in at.metric] == [
        "Units sold",
        "Revenue",
        "Profit",
        "Stockout risk",
    ]


def test_promo_lifts_units_and_risk(at: AppTest) -> None:
    # Daypacks have spare supply in the promo weeks; jackets sell out, so a
    # jacket promo mostly moves demand forward instead of adding units.
    at.segmented_control(key="product").set_value("Daypacks").run()
    at.slider(key="promo").set_value(20).run()
    assert not at.exception
    assert metric(at, "Units sold").delta.startswith("+")
    assert metric(at, "Stockout risk").delta.startswith("+")
    # The brief explains what the promo did to profit.
    assert any("20% promo" in m.value for m in at.markdown)


def test_switching_products_resets_the_levers(at: AppTest) -> None:
    at.slider(key="price").set_value(10).run()
    at.segmented_control(key="product").set_value("Tents").run()
    assert at.slider(key="price").value == 0
    assert at.slider(key="marketing").value == 10.0


def test_pricing_and_scenarios_pages_render(at: AppTest) -> None:
    at.switch_page("app_pages/pricing.py").run()
    assert not at.exception
    assert metric(at, "Profit-maximizing price").value.startswith("$")
    at.switch_page("app_pages/scenarios.py").run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 3  # The example scenarios
