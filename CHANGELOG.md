# Changelog

All notable changes to this project will be documented in this file.

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
