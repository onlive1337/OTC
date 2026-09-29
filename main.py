import asyncio
import importlib
import logging
import sqlite3
import sys
import ujson
from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector

from config.config import (
    LOG_LEVEL,
    HTTP_TOTAL_TIMEOUT,
    HTTP_CONNECT_TIMEOUT,
    CACHE_EXPIRATION_TIME,
    HTTP_CONNECTOR_LIMIT,
    HTTP_CONNECTOR_LIMIT_PER_HOST,
    HTTP_DNS_CACHE_TTL,
    POLLING_CONCURRENCY,
    RATE_REFRESH_RETRY_INTERVAL,
)
from loader import bot, dp, user_data
from utils.http import set_http_session, close_http_session, safe_bg_task
from utils.rates import get_exchange_rates, refresh_rates, close_rate_refresh, get_cached_data
from utils.log_handler import setup_telegram_logging

from utils.middleware import RateLimitMiddleware, ErrorBoundaryMiddleware

from handlers import general, admin, settings, conversion

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s %(levelname)s [%(name)s]: %(message)s'
)
logger = logging.getLogger(__name__)

_bg_tasks = []

async def _warmup_rates():
    try:
        if await get_exchange_rates():
            logger.info("Rates cache warmed up")
        else:
            logger.warning("Rate warmup returned no rates")
    except (ClientError, asyncio.TimeoutError, RuntimeError, ValueError, TypeError, KeyError):
        logger.exception("Warmup failed")

async def _periodic_refresh():
    normal_interval = max(CACHE_EXPIRATION_TIME - 60, 60)
    interval = RATE_REFRESH_RETRY_INTERVAL
    while True:
        await asyncio.sleep(interval)
        try:
            await refresh_rates(force=True)
            interval = normal_interval if get_cached_data('exchange_rates') else RATE_REFRESH_RETRY_INTERVAL
        except asyncio.CancelledError:
            raise
        except (ClientError, asyncio.TimeoutError, RuntimeError, ValueError, TypeError, KeyError):
            interval = RATE_REFRESH_RETRY_INTERVAL
            logger.exception("Periodic rate refresh failed, retrying in %ds", interval)

async def on_startup():
    await setup_telegram_logging(bot)
    session = ClientSession(
        timeout=ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT),
        connector=TCPConnector(
            limit=HTTP_CONNECTOR_LIMIT,
            limit_per_host=HTTP_CONNECTOR_LIMIT_PER_HOST,
            ttl_dns_cache=HTTP_DNS_CACHE_TTL,
        ),
        json_serialize=ujson.dumps
    )
    set_http_session(session)
    
    await user_data.init_db()
    
    _bg_tasks.append(safe_bg_task(_warmup_rates(), name="warmup_rates"))
    _bg_tasks.append(safe_bg_task(_periodic_refresh(), name="periodic_refresh"))

async def on_shutdown():
    for task in _bg_tasks:
        task.cancel()
    for task in _bg_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _bg_tasks.clear()
    await close_rate_refresh()
    try:
        await close_http_session()
    except RuntimeError:
        logger.exception("Error during HTTP session shutdown")
    try:
        await user_data.close()
    except sqlite3.Error:
        logger.exception("Error closing database connection")

async def main():
    dp.message.middleware(ErrorBoundaryMiddleware())
    dp.message.middleware(RateLimitMiddleware(limit=5, window=3.0))

    dp.callback_query.middleware(ErrorBoundaryMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware(limit=8, window=3.0))

    dp.inline_query.middleware(ErrorBoundaryMiddleware())
    dp.inline_query.middleware(RateLimitMiddleware(limit=5, window=3.0))

    dp.include_router(general.router)
    dp.include_router(admin.router)
    dp.include_router(settings.router)
    dp.include_router(conversion.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        tasks_concurrency_limit=POLLING_CONCURRENCY,
    )

def run_app():
    if sys.platform != 'win32':
        try:
            _uvloop = importlib.import_module("uvloop")
        except ModuleNotFoundError:
            _uvloop = None

        if _uvloop is not None:
            with asyncio.Runner(loop_factory=_uvloop.new_event_loop) as runner:
                runner.run(main())
            return

    asyncio.run(main())

if __name__ == '__main__':
    try:
        run_app()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
