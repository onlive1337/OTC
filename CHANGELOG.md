# Changelog

All notable changes to this project will be documented in this file.

## Changelog

## [1.8.2] - 2026-04-16

### ♻️ Refactor
- Migrated uvloop startup path to `asyncio.Runner(loop_factory=uvloop.new_event_loop)` for Python 3.14+ compatibility.
- Removed deprecated global event-loop policy setup from `loader.py`.
- Added public APIs to avoid protected-member access in app code (`ping_db`, `safe_bg_task`).


### ⚡ Performance
- Moved aiohttp connector tuning to config (`HTTP_CONNECTOR_LIMIT`, `HTTP_CONNECTOR_LIMIT_PER_HOST`, `HTTP_DNS_CACHE_TTL`) and applied the same limits to startup and fallback HTTP sessions.

### 🛡️ Stability
- Added SQLite lock-resilience pragmas: `busy_timeout` and `wal_autocheckpoint` for read/write connections.
- Added the same SQLite pragmas to initial schema setup for consistent behavior on fresh databases.

### 🐛 Fixes
- Hardened amount parser: invalid formats like `100.5.5 USD` and oversized values (`>1e100`) are now rejected.
- Added explicit scientific notation boundary behavior: `1e100` is accepted, `1e101+` is rejected.
- Improved UX for failed conversion parses: bot now replies with a clear amount-format/size hint instead of silent ignore when currency is recognized.

### 🧪 Testing
- Added parser boundary regression test for `1e100 USD`.

## [1.8.1] - 2026-04-11

### ✨ New Features
- **Unknown Currency Warning**: Bot now warns when an unrecognized currency is entered (e.g., `300 bny`) and suggests similar codes (`BYN`, `BNB`, `CNY`) using fuzzy matching.
- **Standalone Math Calculator**: Pure math expressions without a currency (e.g., `50+50`, `1000*3-20`, `100/4`) now return calculated results.

### 🔧 Other
- Added `unknown_currency`, `unknown_currency_no_suggestions`, and `math_result` localization strings for RU/EN.

## [1.8.0] - 2026-02-28

### ⚡ Performance
- **True Parallel API Fetching**: Fiat and crypto rates now fetch simultaneously via `asyncio.gather` — previously sequential despite v1.7.0 claiming parallelism.
- **Deferred DB Write**: `update_user_data` now only called when a valid conversion is found, not on every incoming message.
- **Cache-First Data Access**: `get_user_data()` and `get_chat_data()` check in-memory cache before hitting SQLite.
- **Removed DB Health Ping**: Eliminated per-call `SELECT 1` from `_get_conn()` — unnecessary for local SQLite.
- **Removed Duplicate Queries**: Eliminated redundant `get_user_language` in `/settings` and duplicate `update_user_data` in `process_multiple_conversions`.

### 🛡️ Stability
- **Race Condition Fixes**: `_ensure_user` and `_ensure_chat` now perform SELECT+INSERT under a single `_write_lock` — eliminates concurrent registration race.
- **CancelledError Handling**: `_bg_refresh_rates` now explicitly re-raises `CancelledError` before `finally`, preventing `_revalidating` flag from getting stuck.
- **Group Language Enforcement**: `ErrorBoundaryMiddleware` now sends error messages using the chat's language in groups, not the user's personal language.
- **Log Buffer Safety**: `_flush_buffer` now uses `_buffer_lock` — prevents log entries from being lost during concurrent emit/flush.
- **Broadcast Counter Safety**: Replaced `nonlocal` counters with a dict in broadcast to avoid potential concurrent mutation issues.
- **Missing Callback Answers**: Added `callback_query.answer()` to `back_to_main`, `process_settings`, and `back_to_settings` — eliminates remaining 30s loading spinners.

### 🧹 Cleanup
- Removed unused `original_text` variable in `parse_amount_and_currency`.

## [1.7.0] - 2026-02-21

### ⚡ Performance
- **Parallel API Requests**: CoinGecko and fiat sources now fetch concurrently.
- **O(1) Currency Lookup**: Replaced O(n) pattern scanning with dict lookup in targeted conversion.
- **Batched DB Queries**: `process_conversion`, `process_multiple_conversions`, `inline_query_handler`, and `process_targeted_conversion` now use a single `get_user_data()`/`get_chat_data()` call instead of 3-5 separate queries.
- **Sync Cache Access**: `get_cached_data`/`set_cached_data` no longer async — removed unnecessary coroutine overhead.
- **Lazy Language Loading**: `handle_message` defers language query until actually needed.

### 🛡️ Stability
- **Safe Log Handler**: `TelegramLogHandler.emit()` now checks for a running event loop before creating tasks — prevents `RuntimeError` in sync contexts.
- **Batched Broadcast**: Replaced unbounded `asyncio.gather` with batched processing (100 users/batch) with progress reporting.
- **Race Condition Fix**: Eliminated unsafe `_rates_lock.locked()` check — replaced with atomic `_revalidating` flag.
- **Callback Answers**: Added `callback_query.answer()` to all settings handlers (`user_settings` + `chat_settings`) — no more 30s loading spinners.

### 🗑️ Removed
- **NOT, DUREV, HMSTR**: Removed these tokens and the CryptoCompare API dependency.
- **CryptoCompare**: Entire API integration removed — all crypto now sourced from CoinGecko.

### 🔧 Other
- Updated `uvloop` requirement to `>=0.21.0` with platform marker for Python 3.14 compatibility.
- Removed unused `min-api.cryptocompare.com` semaphore limit.

## [1.6.0] - 2026-02-13

### 🛡️ Stability Improvements
- **Zero Division Protection**: Added validation for zero rates in currency conversion.
- **Memory Leak Fixes**: Fixed memory leaks in RateLimitMiddleware, user cache, and chat cache with automatic cleanup.
- **Retry Limits**: Added max retry limit (3) to RetryMiddleware to prevent infinite loops.
- **Fallback Cache**: Exchange rates now use stale cache as fallback when all APIs fail.
- **Graceful Shutdown**: Added proper SIGTERM/SIGINT handling for Docker deployments.
- **Timeout Protection**: Added 30s timeout for periodic rate refresh to prevent hangs.
- **DoS Protection**: Added message length limit (500 chars) and conversion limit (10 per message).
- **Inline Query Protection**: Added length limit (100 chars) for inline queries.

### ⚡ Performance Optimizations
- **SQLite Tuning**: Added `cache_size=64MB`, `mmap_size=256MB`, `temp_store=MEMORY`, `PRAGMA optimize`.
- **Database Indexes**: Added indexes for `user_currencies`, `user_crypto`, `chat_currencies`, `chat_crypto` tables.
- **Query Optimization**: Combined 3 separate queries into 1 for `get_user_data` and `get_chat_data`.
- **Log Batching**: Telegram log handler now buffers and batches multiple errors.

### 🧪 Testing
- Added tests for zero rate protection, missing currencies, and edge cases.
- Total: 50 tests passing.

## [1.5.0] - 2026-02-13

### 🐳 Infrastructure & Docker
- **Docker Support**: Full Dockerization with `Dockerfile` and `docker-compose.yml`.
- **Production Ready**: Database persistence via bind-mounts (`./data`).
- **Optimization**: Added `uvloop` for faster event loop and `ujson` for rapid JSON processing.

### 🌐 Logic & Internal
- **Chat Language Enforcement**: Group interactions (conversions, errors, help) now strictly follow the **Group's Language**, ignoring the user's personal language settings.
- **Admin Rights**: Fixed "Admin Only" error message language to match the group's context.
- **Async I/O**: Cached `CHANGELOG.md` reading (memory insted of disk) and optimized admin logging.

## [1.4.0] - 2026-02-10

### ✨ New Features
- **Targeted Conversion**: convert to specific currency (e.g., `100 USD EUR`).
- **Broadcast**: `/broadcast` command for mass messaging (supports text, photo, video).
- **Improved Help**: updated and compact `/help` text.
- **Styled Buttons**: all buttons are now styled with emojis and colors.

### 🛠 Technical Improvements
- **SQLite Auto-Reconnect**: automatic database connection recovery.
- **Middlewares**: added Rate Limiting (anti-spam) and Auto-Retry (message queuing).
- **Healthcheck**: `/health` command for monitoring bot status.
- **Refactoring**: optimized keyboard handling and safe background task execution.
- **Removed numpy**: removed numpy dependency.

## [1.3.0] - 2025-11-19

### Added
- **Async Database**: Migrated from `sqlite3` to `aiosqlite` for non-blocking database operations.
- **Modular Architecture**: Refactored `main.py` into a modular structure with `handlers/`, `loader.py`, and `states/`.
- **Routers**: Implemented `aiogram` Routers for better code organization and scalability.
- **Shared Loader**: Introduced `loader.py` for singleton management of `bot` and `user_data`.

### Changed
- **Performance**: Improved bot responsiveness by removing blocking synchronous database calls.
- **Code Structure**: Split the monolithic `main.py` into smaller, maintainable modules.

## [1.2.0] - 2025-10-09

### Added
- Local SQLite storage (otc.db) instead of JSON; automatic table creation and PRAGMA WAL.
- Global aiohttp ClientSession for the entire lifetime of the application; warming up the course cache at startup.
- Retries with exponential delay and parallelism limitation (semaphores) for HTTP requests to exchange rate providers.
- Stale-While-Revalidate (SWR) cache mode for exchange rates.
- Healthcheck in Dockerfile.
- Anti-flood for Telegram logs; only ERROR messages are sent to the log chat.

### Changed
- Complete removal of JSON files; constants and calls related to JSON have been removed. docker-compose now mounts the ./data directory and uses DB_PATH=/app/data/otc.db.
- Centralized logging (basicConfig in main.py); duplicate basicConfig from modules removed.
- Number formatting: M/B abbreviations disabled for fiat currencies — now the full value is displayed with separators.

### Removed
- /price command and the entire crypto chart feature (Binance/Coingecko history, matplotlib rendering). The bot no longer builds or sends crypto price charts.

### Fixed
- Fixed the critical error “Session is closed” and other issues when receiving rates; added timeouts, retries, and value checks (no division by zero/KeyError).
- TelegramBadRequest handling: “message is not modified” is ignored when re-editing a message in settings.
- User and chat settings: if all currencies/cryptocurrencies are removed, defaults are no longer substituted, and the corresponding sections are hidden.

## [1.1.1] - 2025-05-30

### Added

- Strings for conversion_help_message string

### Fixed

- Trigger System

## [1.1.0] - 2025-02-03

### Added

- ARS,  VND, BGN, HRK currencies
- Crypto graphics /price (for exact crypto use /price TON)

### Changed

- Rewrite the parsing system from scratch

### Fixed (1.0.9)

- USDT price display issue
- Error handling for invalid crypto pairs
- Message deletion in price callback

## [1.0.9] - 2024-12-09

### Fixed

- Bugs with binary queries (aka 20k sum and 20k rubles)
- Bugs with parsing text with comma

---

Note: The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
