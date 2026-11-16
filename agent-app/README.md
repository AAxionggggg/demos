# Cairn Analyst — an agent app

An AI analyst for Cairn, a fictional outdoor retailer. People ask about sales,
demand, and inventory in a chat, and the agent shows its work as it goes: its
steps appear in a timeline, the answer streams in, and every reply carries live
metrics and charts. The full analysis opens in a side drawer, the canvas, and
purchase orders the agent drafts wait there for a person to approve.

- **Why did West revenue fall?** A revenue bridge from the week before to last
  week: the Summit down jacket sold out online, a wholesale order slipped, and
  a trail runner launch offset part of it. The canvas has the trend, the change
  by channel and category, and the query.
- **Compare prices:** a Monte Carlo simulation of three prices for the jacket
  (2,000 futures each, run in NumPy on every request), with margin ranges,
  weekly units against supply, and the simulation's source.
- **Draft restock orders:** six purchase orders sized to whole cases. Nothing is
  ordered until you approve: edit quantities and approve them in the canvas,
  with guardrails checked on the server.
- **Summarize the week:** a leadership update with KPI sparklines, ready to
  download as Markdown.
- **Attach a file:** CSV, TSV, and JSON files are profiled for real (columns,
  gaps, and a chart of the time series they contain).

No model is called and no API key is needed. `utils/agent.py` plays back
scripted analyses, but every number in them is computed in Python from the
synthetic data in `utils/data.py`, so the text, the charts, and the canvas
always agree. Anything else gets an honest "this demo can't answer that" with
suggestions.

## What it shows

| Capability | API |
| --- | --- |
| Chat history with a custom avatar | `st.chat_message`, `st.session_state` |
| Attach files, and stop a long run from the input | `st.chat_input(accept_file="multiple", file_type=..., submit_mode="stop")` |
| "Thought for N seconds" over a timeline of tool calls | `st.status(type="compact")` around `st.status(type="step")`, with `:shimmer[...]` labels while each step runs |
| The answer streams in | `st.write_stream(..., cursor=...)` |
| Feedback on every answer, follow-up suggestions | `st.feedback("thumbs")`, `st.pills` |
| A canvas with the full analysis | `@st.dialog(position="right")` with `st.tabs` |
| People approve what the agent proposes | `st.data_editor` with `CheckboxColumn`, server-side validation |
| KPI cards with trends | `st.metric(chart_data=..., delta_description=...)` in `st.grid` |
| Waterfall, box plot, and trend charts | `st.echarts_chart` |
| Connected data in the sidebar | `st.table(border="horizontal", hide_header=True)` |
| Download the conversation or the update | `st.download_button` |
| A warm ivory theme with a serif for headings, light and dark; charts take their colors from it | `.streamlit/config.toml` (Source Serif 4 and DM Sans, CVD-checked chart palette) |
| Headless tests | `streamlit.testing.v1.AppTest` in `tests/` |

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
pytest tests
```

**Settings** in the sidebar hides the steps while the agent works, or skips the
demo's pauses. `requirements.txt` pins a preview build of Streamlit with the
latest chat and layout changes. Switch to a release once one ships them.

## Use a real model

Keep the `Reply` shape in `utils/agent.py` and build it from your model or
agent framework: each tool call becomes a `Step`, and the model's streamed text
goes to `st.write_stream`. For example, with any client that streams text:

```python
with st.chat_message("assistant"):
    with st.status(":shimmer[Thinking]", type="compact") as thinking:
        for call in agent.tool_calls(prompt):  # your framework's events
            with st.status(call.name, type="step", state="complete"):
                st.write(call.result)
        thinking.update(label="Thought for 4 seconds", state="complete")
    answer = st.write_stream(agent.stream_answer(prompt))
```

Keep API keys in `.streamlit/secrets.toml` and read them with `st.secrets`.
