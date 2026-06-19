# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Home Smart Assistant — a Vietnamese-speaking AI butler for a smart home. It chats with the
homeowner, answers questions grounded in their documents (RAG), personalizes suggestions, and
controls devices via tool calling. It uses an off-the-shelf model with no fine-tuning. The
document store can auto-refresh from configured news sources each morning instead of manual upload.

## Commands

All commands run from the project root.

```bash
pip install -r requirements.txt          # install deps

python scripts/ingest_once.py            # one-time: load data/articles into the vector store
python scripts/butler_cli.py             # chat with the butler (streaming) in the terminal
uvicorn api.server:app                    # serve the API (POST /chat, /update, GET /health)

python scripts/crawl.py                   # crawl URLs from data/sources.txt, then ingest
python scripts/crawl.py <url> <url>       # crawl specific URLs
python scripts/crawl.py --site <url> --max 30   # crawl one whole domain
python scripts/crawl.py ... --no-ingest   # crawl without ingesting

python scripts/scheduler.py               # run the daily-update scheduler as its own process
python -m app.watcher                     # auto-ingest when data/articles changes
```

Module entry points also work directly: `python -m app.butler`, `python -m app.scheduler`.

There is **no test suite, linter, or build step** configured in this repo.

## Runtime prerequisite

The LLM is reached through an **OpenAI-compatible endpoint**. Locally this is Ollama, which must
be running with two models pulled:

```bash
ollama pull qwen3:8b            # chat model — MUST support tool calling
ollama pull nomic-embed-text    # embedding model
```

To move to production (e.g. vLLM on AWS), set `LLM_BASE_URL` to the new endpoint — no code change.
All config lives in `config.py`, overridable via env vars / `.env` (see `.env.example`).

## Architecture

The request flow for a chat turn:

`scripts/butler_cli.py` or `api/server.py` → `app/butler.py` → `app/llm.py` (OpenAI client)
→ model returns tool calls → `app/tools.py` executes them → results fed back to the model.

- **`app/butler.py`** — the agent loop. `chat()` (non-streaming, used by the API) and
  `chat_stream()` (streaming, used by the CLI and a hook for future TTS) both run a bounded
  tool-calling loop (`MAX_STEPS = 5`). Two deliberate behaviors live here:
  - **Confirmation gating** is enforced by the *system prompt*, not code: simple reversible
    actions (lights/fans) execute immediately; high-impact/ambiguous ones (turn off everything,
    extreme temperatures) must ask the user first.
  - **Direct-reply latency optimization**: tools in `DIRECT_REPLY_TOOLS` (the device-control
    tools) return a ready-made confirmation string that is spoken verbatim, skipping one extra
    model round-trip. If you add a control tool, consider adding it to that set.
- **`app/tools.py`** — the tool registry. `TOOLS` is the OpenAI tool-schema list; `_REGISTRY`
  maps names to functions; `execute(name, args)` dispatches. Device control acts on an in-memory
  `HOME` dict (simulated) — replace the function bodies with real device API calls in production;
  keep the `TOOLS` declarations unchanged.
- **`app/memory.py`** — long-term homeowner *preferences*, stored in `data/memory.json`,
  **kept separate from the document store** so unvetted preferences never mix into trusted
  knowledge. Preferences are injected directly into the system prompt (`memory.as_text()` in
  `butler._system()`); written only via the `remember_preference` tool when the user states a
  clear preference.
- **`app/weather.py`** — outdoor weather via Open-Meteo (free, no API key), located by
  `HOME_LAT`/`HOME_LON` in `config.py`. `current_text()` is cached in-memory and never raises
  (returns a short fallback line on any error). Surfaced as the `get_weather` tool.
- **`app/calendar_store.py`** — local event calendar in `data/events.json` (a JSON list of
  `{date, time, title}`). Surfaced as the `get_calendar` / `add_event` tools. The current
  date/time is also injected into every system prompt by `butler._now_text()`, so the model is
  time-aware without a tool call.

The RAG / ingestion side:

- **`app/documents.py`** — reads `.txt`/`.md`/`.pdf`, chunks with overlap.
- **`app/vector_store.py`** — thin wrapper over a persistent Chroma collection (lazy-initialized).
  Swapping to Qdrant/pgvector means rewriting only this file.
- **`app/ingest.py`** — incremental ingestion keyed by a content-hash **manifest**
  (`data/manifest.json`): unchanged files are skipped, changed files are deleted-and-re-added,
  and files removed from the directory are purged from the store. Source filename is the metadata
  key tying chunks back to a document.
- **`app/crawler.py`** — fetches web pages, extracts main content with trafilatura, saves Markdown
  into `data/articles/`. Respects `robots.txt` (fetched with the real User-Agent and cached per
  host) and sleeps `CRAWL_DELAY` between requests.
- **`app/scheduler.py`** — `daily_update()` crawls every URL in `data/sources.txt` then ingests.
  Runs either as a standalone blocking process (`start_blocking`) or embedded in the API as a
  background APScheduler job (`start_background`, wired into the FastAPI lifespan). Skipped
  entirely when `sources.txt` is empty. Default time 06:00, via `DAILY_UPDATE_HOUR/MINUTE`.
- **`app/watcher.py`** — watchdog-based alternative that re-ingests on filesystem changes.

`data/` holds runtime state — `chroma_db/`, `manifest.json`, `memory.json` are all generated.

## Conventions

- **Comments, docstrings, and user-facing strings are Vietnamese written in ASCII** (no diacritics,
  e.g. "Tra ve trang thai"). Match this style when editing existing files. README is full Vietnamese.
- `config.py` is the single source of truth for settings; read values from it rather than
  hardcoding, and add new knobs there with an env-var fallback.
