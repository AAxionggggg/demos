# Cairn Demand lab — a forecasting app

**Live demo:** [forecasting-app-demo.streamlit.app](https://forecasting-app-demo.streamlit.app/)

A what-if demand and pricing simulator for Cairn, a fictional outdoor retailer.
Planners pull levers (price, a promo and its weeks, marketing spend, supply)
and every change reruns a Monte Carlo simulation of the next 26 weeks in
Python, next to the data. The computation and the interface are the same code.

- **Forecast:** KPI cards with sparklines, a weekly fan chart (median, 50% and
  80% ranges, last year, supply), the distribution of season revenue against
  the target, a tornado chart of what moves profit, and a plain-language brief
  computed from the same simulations.
- **Pricing:** the price-response curve with the profit-maximizing price, and a
  profit surface over price and marketing. Click a cell to apply its levers.
- **Scenarios:** save scenarios, compare their medians, spread of outcomes
  (boxplot), and weekly units, then load one back.

All data is synthetic. To use your own, replace `model.load_history` with a
query and fit the `Product` parameters from your data.

## What it shows

| Capability | API |
| --- | --- |
| Shareable scenarios: every lever lives in the URL | `bind="query-params"` on sliders and segmented controls |
| Layout-first loading, cards load concurrently | `st.skeleton` + `@st.fragment(parallel=True)` |
| Repeat scenarios are instant | `st.cache_data` with `max_entries` |
| Fan, histogram, tornado, heatmap, boxplot charts | `st.echarts_chart` |
| Click a heatmap cell to apply its levers | `st.echarts_chart(on_select=callback)` |
| KPI cards with trends and deltas vs. plan | `st.metric(chart_data=..., delta_description=...)` |
| Row actions in a table | `st.column_config.ButtonColumn` |
| Save dialog, export | `@st.dialog`, `st.form`, `st.download_button` |
| A warm editorial theme: serif headings, paper tones, pill buttons, light and dark | `.streamlit/config.toml` (Fraunces and Instrument Sans, CVD-checked chart palette) |
| Headless tests | `streamlit.testing.v1.AppTest` in `tests/` |

The simulation uses common random numbers: every scenario of a product line
sees the same simulated futures, so the differences between scenarios come
from the levers alone.

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
pytest tests
```

`requirements.txt` pins a preview build of Streamlit with the latest skeleton
and layout changes. Switch to a release once one ships them.

## Use it as a tool

Agents can drive the same app over HTTP, through the same cached simulation
people see. Start it with the agent API on:

```bash
streamlit run streamlit_app.py --server.enableAgentApi=true --server.port=8765
```

Then set levers by key and read the metrics back as data:

```bash
SESSION=$(curl -s -X POST localhost:8765/_stcore/agent/interact -d '{}' | jq -r .session_id)
curl -s -X POST localhost:8765/_stcore/agent/interact \
  -d "{\"session_id\": \"$SESSION\", \"widget_state\": {\"promo\": 20, \"supply\": 115}}" \
  | jq '[.. | objects | select(.type == "metric") | {label: .props.label, value: .props.value, delta: .props.delta}]'
```

The same protocol is served as an MCP server at `/_stcore/agent/mcp`.
