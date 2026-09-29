# Financial Assistant

Interactive LangChain investment-brief prototype for your confirmed Indian equity holdings.

## Start here

Extract this project into a **new folder** instead of copying it over the old project (otherwise removed files will remain). Keep the original as a backup.

From this project root:

```bash
poetry install
cp .env.example .env
```

Copy your existing `OPENAI_API_KEY` and `DATABASE_URL` values into `.env`. Your credentials and Mac virtual environment are not included. The model stays in `config.yaml`. Use the same Neon database to retain your existing holdings and quotes; no schema change is required for the new CLI.

```bash
poetry run financial-assistant --user-id demo_user --session 2026-09-25
```

Then enter:

```text
/portfolio
/brief
/ask Which of my stocks had the largest daily decline in the selected session?
/ask What does daily percentage change mean?
/session 2026-09-24
/status
/help
/exit
```

`/session` changes which stored price session to query. It does not fetch data; missing prices will be reported as unavailable. `/portfolio` uses the database without calling the LLM. Each `/ask` is standalone: conversation memory is not enabled.

The portfolio defaults to the latest confirmed snapshot on or before today's date in India. Set `--holdings-as-of 2026-09-25` to select an older portfolio explicitly. Prices, holdings, and news have separate dates. User ID is local prototype routing, **not authentication**; do not expose this CLI as a multi-user service without auth.

One-shot operation remains available:

```bash
poetry run financial-assistant --user-id demo_user --session 2026-09-25 --once
poetry run python examples/run_investment_brief.py --user-id demo_user --session 2026-09-25
```

Alternatively run `poetry run python -m financial_assistant` with the same arguments.

## What is connected

- Confirmed portfolio snapshots in Neon.
- Validated historical NSE EQ closing prices from the bhavcopy pipeline.
- Optional stored RSS summaries: add `--rss` at launch. The news window is calculated automatically as the last 24 hours. This does not fetch a fresh feed, guarantee complete coverage, or read attachments.
- **No live web search, Zerodha Pulse collector, or current-news research is connected yet.** The agent must disclose that limitation. This is not yet the complete daily research brief.

## How the code fits together

`cli.py` reads commands and displays results. `features/investment_brief/service.py` loads portfolio context, separates dates, and constructs the request. `agent/factory.py` builds the LangChain agent and selects tools. `agent/orchestrator.py` invokes it with configured timeout/recursion limits and checks required tool calls for a brief. Tools retrieve evidence from Neon.

The factory builds the agent once per CLI session, but requests have independent message lists. Tool-call presence is checked; it does not establish source success or complete coverage. Tool failures remain explicit in results.

Ingestion is separate: loading stored data does not refresh it. The application never schedules jobs automatically.

## Existing data workflows

Run examples from the project root. Examples contain the initial six-symbol prototype scope.

- `examples/run_market_ingestion.py --session DATE`: download and validate bhavcopy (does not save to Neon).
- `examples/save_market_snapshot.py --file PATH --session DATE`: persist validated quotes.
- `examples/extract_portfolio.py --file PATH --save-draft --user-id demo_user`: extract and save a draft.
- `examples/review_portfolio.py --user-id demo_user --version-id 1`: review and confirm.
- Existing RSS and announcement/PDF scripts are retained as optional experiments. Their sample paths/dates are not a daily scheduler.
- `examples/setup_market_tables.py --migration FILENAME`: apply migrations for a new database. Retain and apply 001, 002, and (for RSS) 003 in order. Do not edit previously applied migrations.

The included `data/portfolios/sample_portfolio.pdf` is synthetic. Source download fixtures and previous extraction results are preserved for reproducibility; do not interpret them as refreshed data.

If using the browser downloader for the first time:

```bash
poetry run playwright install chromium
```

## Cleanup in this version

- Added the interactive CLI and shared service; replaced the duplicate one-shot runner with a compatibility wrapper.
- Removed required-but-unused news-start/news-end flags.
- RSS is now opt-in instead of being forced into every request.
- Removed obsolete NSE market MCP discovery/date-probe scripts and their unused `mcp` adapter package. The existing MCP dependency remains locked for the planned search integration.
- Removed one duplicated early RSS capture, Mac metadata, and Python caches from the delivery.
- Excluded local credentials and platform-specific environments. Added `.env.example` and project ignore rules.
- Retained migrations, database repositories, ingestion code and source fixtures. No database records were changed or deleted.

## Validation

```bash
poetry run python -m unittest discover -s tests -v
```

Tests exercise CLI routing, date separation, automatic RSS windows, error recovery, and LLM-free portfolio display with test doubles. Live OpenAI and Neon calls require your credentials and were not executed while preparing this delivery.
