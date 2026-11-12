# Cairn Reorder desk — an app that acts

Planners at Cairn, a fictional outdoor retailer, review the purchase orders an
AI replenishment agent proposes every morning. They adjust quantities, then
approve, hold, or reject each order, and every decision is checked against
guardrails and written back to the database. The decision happens in the same
app as the data.

- **Review queue:** KPIs, filters, and an editable table of today's proposals.
  Edit quantities, pick decisions, add notes, accept every low-risk proposal in
  one click, and submit. **Review** opens a drawer with the agent's reasoning
  as a step timeline, projected stock with and without the order, demand, and
  a decision form.
- **Activity:** the audit log, decisions per day by outcome, and where planners
  trust the agent (share approved unchanged, by category).
- **Guardrails:** edit the limits per category (auto-approve threshold, order
  cap, note threshold, confidence floor) and see their effect on the open queue
  before saving.

The data is synthetic. Because this is a public demo, every browser session gets
its own SQLite database seeded with today's agent run, so one visitor's
decisions never change what others see. **⋮ → Reset demo data** starts over. A
real team shares one database: write your agent's output instead of
`utils/seed.py`, point `store.connection` at your warehouse, and cache the reads
with `st.cache_data`, clearing them after each write. A proposal that is already
decided is skipped, so two planners can't decide it twice.

## What it shows

| Capability | API |
| --- | --- |
| A review queue people edit like a spreadsheet | `st.data_editor` with `NumberColumn`, `SelectboxColumn`, `TextColumn` |
| Badges, confidence bars, row actions | `MultiselectColumn`, `ProgressColumn`, `ButtonColumn` |
| Drafts that survive filters and searches | `on_change` callback into `st.session_state` |
| Validation on the server before any write | `utils/rules.py` (whole cases, order caps, required notes) |
| Writeback and an audit log | `st.connection(type="sql")` with SQLAlchemy |
| A database per session, closed when idle | `st.connection(..., max_entries=500, ttl=3600)` |
| The agent's reasoning, step by step | `st.status(type="step")` |
| A side drawer with a decision form | `@st.dialog(position="right")` + `st.form` |
| Filters in the URL, live search | `bind="query-params"`, `st.text_input(live=True)` |
| Charts | `st.echarts_chart` |
| A teal brand theme with Plus Jakarta Sans, light and dark; charts take their colors from it | `.streamlit/config.toml` (CVD-checked chart palette) |
| Headless tests | `streamlit.testing.v1.AppTest` in `tests/` |

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
pytest tests
```

Each session creates its database in the temp folder. `requirements.txt` pins a
preview build of Streamlit with the latest skeleton and layout changes. Switch
to a release once one ships them.

## Use it as a tool

Agents can work the queue over HTTP through the same validation and writeback
as people. The editable table is browser-only, so agents use **Review next**
and the drawer's form, or accept the low-risk proposals in bulk:

```bash
streamlit run streamlit_app.py --server.enableAgentApi=true --server.port=8765

SESSION=$(curl -s -X POST localhost:8765/_stcore/agent/interact -d '{}' | jq -r .session_id)
call() { curl -s -X POST localhost:8765/_stcore/agent/interact -d "$1"; }

# Open the most urgent proposal; the drawer's widget keys end in its PO number
PO=$(call "{\"session_id\": \"$SESSION\", \"trigger\": {\"key\": \"review_next\"}}" \
  | jq -r '[.. | objects | select(.type == "number_input") | .key][0] | ltrimstr("qty_")')

# Reject it without a note: the guardrail answers "Add a note to reject"
call "{\"session_id\": \"$SESSION\", \"trigger\": {\"key\": \"reject_$PO\"}}" \
  | jq '[.. | objects | select(.type == "error") | .props.body]'

# Or approve every low-risk proposal and submit them
call "{\"session_id\": \"$SESSION\", \"trigger\": {\"key\": \"accept_low_risk\"}}" > /dev/null
call "{\"session_id\": \"$SESSION\", \"trigger\": {\"key\": \"submit\"}}" > /dev/null
```

The same protocol is served as an MCP server at `/_stcore/agent/mcp`.
