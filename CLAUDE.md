# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

OTC is an aiogram 3.x Telegram bot that converts between fiat currencies and cryptocurrencies. It handles free-text messages ("100 USD", "5к рублей", "100+50 EUR"), inline queries, and per-user / per-chat settings. Primary languages are Russian (`ru`, default) and English (`en`).

## Commands

```bash
# Install deps (Python 3.14 both locally in .venv and in Docker)
pip install -r requirements.txt

# Run the bot (requires TELEGRAM_BOT_TOKEN in .env)
python main.py

# Run all tests
pytest

# Run a single test class or case
pytest tests/test_utils.py::TestSmartNumberParse
pytest tests/test_utils.py::TestParseAmountAndCurrency::test_simple_integer -v

# Docker
docker compose up --build
```

Tests are pure-unit and live in `tests/`: `test_utils.py` (parser, `convert_currency`, formatter), `test_rates.py` (`normalize_fiat_payload`, the rate cache, USD-pivot conversion), and `test_data.py` (DB layer against a temp SQLite file, run via `asyncio.run` — there is no `pytest-asyncio`, so each test must do all its DB work inside one `_run()` call). There is no lint config; match existing style.

## Configuration

All config is environment-driven via `config/config.py` (loads `.env`). `TELEGRAM_BOT_TOKEN` is required and raises at import if missing. Other vars: `ADMIN_IDS` (comma-separated, gates the admin handlers), `LOG_CHAT_ID` (Telegram chat to mirror logs into), `COINCAP_API_KEY` (optional crypto fallback), `DB_PATH`, `LOG_LEVEL`, `DB_BACKUP_INTERVAL_HOURS`/`DB_BACKUP_KEEP` (SQLite auto-backup, see Operational constraints). `CURRENT_VERSION` in this file is bumped on release alongside `CHANGELOG.md`.

The supported-currency universe is defined entirely in `config/config.py` as module-level dicts: `ALL_CURRENCIES`, `CRYPTO_CURRENCIES` (the rest are `ACTIVE_CURRENCIES`), `CURRENCY_SYMBOLS`, `CURRENCY_ABBREVIATIONS` (multilingual word forms), and `CRYPTO_ID_MAPPING` (symbol → CoinGecko/CoinCap IDs). To add a currency, update these together — the parser regexes and rate fetchers derive from them at import time.

## Architecture

**Composition root.** `loader.py` builds the singleton `bot`, `dp` (Dispatcher), and `user_data` (the data layer). `main.py` wires middleware, includes the four routers, registers startup/shutdown, and starts polling (uvloop if available). Import `bot`/`dp`/`user_data` from `loader`, never re-instantiate them.

**Handlers** (`handlers/`, one `Router` each, registered in `main.py` in this order): `general` (start/help/menu), `admin` (`/stats`, `/health`, `/broadcast` — admin-gated), `settings` (currency/crypto selection, language, quote format), `conversion` (the core — parses messages and inline queries into conversions). `handlers/conversion.py` is the largest and most complex file; it re-derives its own currency regexes and handles multi-conversion splitting, fuzzy currency suggestions (`difflib`), and math expressions.

**Parsing** (`utils/parser.py`). `parse_amount_and_currency(text)` is the entry point: strips URLs/query-like text, matches a currency via a length-sorted alternation regex built from all currency patterns, then extracts the amount. `smart_number_parse` normalizes mixed thousands/decimal separators (US `1,000.50`, EU `1.000,50`, spaced `10 000`). Multiplier suffixes (`к`/`k`, `млн`/`m`, `млрд`/`b`, etc.) and safe arithmetic (`parse_mathematical_expression`, an AST evaluator restricted to `+ - * /`) are also handled here. This module is the most test-covered — add cases to `tests/test_utils.py` when changing it.

**Rates** (`utils/rates.py`). `get_exchange_rates()` returns a USD-based `{currency: rate}` dict from an in-process `cache` dict with a stale-while-revalidate strategy (`CACHE_EXPIRATION_TIME` fresh window + `STALE_WHILE_REVALIDATE` grace, background refresh via `_revalidation_lock`). Fiat comes from multiple racing sources (first complete set wins); crypto from CoinGecko, with per-symbol CoinCap/CoinGecko fallbacks for anything missing. `convert_currency(amount, from, to, rates)` does USD-pivot math and raises `KeyError`/`ValueError` on missing/zero rates. `main.py` warms the cache on startup and refreshes periodically in a background task.

**HTTP** (`utils/http.py`). A single shared `aiohttp.ClientSession` is set via `set_http_session` in startup and retrieved with `get_http_session`. All external calls go through `_with_retries(coro_factory, host)`, which applies a per-host semaphore (`SEMAPHORE_LIMITS`) and exponential backoff with `Retry-After`/429 handling. Use `safe_bg_task` for fire-and-forget coroutines so exceptions get logged.

**Data layer** (`data/`). `UserData` (`data/user_data.py`) is a single class composed from three mixins: `DatabaseMixin` (`connection.py` — connection lifecycle, schema init/migrations, write lock, in-memory caches, periodic interaction flush), `UserRepoMixin` (`user_repo.py`), and `ChatRepoMixin` (`chat_repo.py`). It uses `aiosqlite` with WAL mode and **separate read and write connections** — all writes serialize through `self._write_lock`; reads use a `query_only` connection. Interaction counters are buffered in `_pending_interactions` and flushed every `FLUSH_INTERVAL` seconds rather than written per-message. Schema and migrations are declarative lists in `data/schema.py` (`INIT_SQL` + numbered `MIGRATIONS`); add a migration by appending a `(version, sql)` tuple. The `*_settings.py` files in `data/` and `settings.py` in `handlers/` hold the settings-UI callback logic, not storage.

**Middleware** (`utils/middleware.py`, applied to message/callback/inline updates in `main.py`): `ErrorBoundaryMiddleware` → `RetryMiddleware` → `RateLimitMiddleware` (per-update-type limits). `_Metrics`/`get_metrics()` here back the admin `/health` command.

**Localization.** `config/languages.py` holds `LANGUAGES[lang][key]` strings. Handlers fetch the user/chat language (`user_data.get_user_language`, defaulting to `ru` for CIS locale codes) and index into `LANGUAGES`. Any new user-facing string needs both `ru` and `en` entries.

## Operational constraints

- **Single instance only.** The rate cache (`utils/rates.py` module-level `cache`), the per-user/per-chat caches (`data/connection.py`), and the rate limiter (`utils/middleware.py`) all live in process memory. Running a second replica would mean two pollers and divergent caches. To scale horizontally these would have to move to shared storage (e.g. Redis). For now, deploy exactly one container (`docker-compose.yml` is written for this).
- **DB backups.** `DatabaseMixin` snapshots the DB via `VACUUM INTO` to `<db dir>/backups/` (so `./data/backups/` on the host) — every `DB_BACKUP_INTERVAL_HOURS` (default 24, `0` disables), keeping the newest `DB_BACKUP_KEEP` (default 7). The schedule keys off the newest backup file's mtime, not process uptime, so container restarts don't reset it.
- **Broadcasts are not restart-safe.** `_execute_broadcast` (`handlers/admin.py`) iterates all users inside the callback task; a restart mid-broadcast aborts it with no resume and no final report. A module-level `_broadcast_in_progress` flag prevents two concurrent broadcasts, but durable/resumable broadcast would need persisted progress.
- **Python version.** Prod runs on `python:3.14-slim` (`Dockerfile`), matching the local `.venv` (3.14). Note that `aiogram` is pinned with `requires_python <3.15`. Don't bump the Docker base image without a container build + in-container `pytest` + smoke test, since it's the prod runtime. `.dockerignore` keeps `.env` and `*.db` out of the image — never weaken that.

## Conventions

- Async throughout; never block the event loop. Wrap background coroutines in `safe_bg_task`.
- Catch concrete exception tuples (`aiohttp.ClientError`, `asyncio.TimeoutError`, `sqlite3.Error`, etc.), not bare `Exception` — this matches the existing degrade-gracefully style where a failed rate source or DB write logs and falls back rather than crashing.
- Bot uses HTML parse mode (set in `loader.py`); format outgoing message text accordingly.
