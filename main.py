import asyncio
import logging
import signal
import ujson
from aiohttp import ClientSession, ClientTimeout

from config.config import LOG_LEVEL, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT, CACHE_EXPIRATION_TIME
from loader import bot, dp, user_data
from utils.utils import get_exchange_rates, set_http_session, close_http_session, _safe_bg_task, refresh_rates
from utils.log_handler import setup_telegram_logging

from utils.middleware import RateLimitMiddleware, RetryMiddleware, ErrorBoundaryMiddleware

from handlers import general, admin, settings, conversion

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s %(levelname)s [%(name)s]: %(message)s'
)
logger = logging.getLogger(__name__)

_bg_tasks = []
_shutdown_event = asyncio.Event()

async def _warmup_rates():
    try:
        await get_exchange_rates()
        logger.info("Rates cache warmed up")
    except Exception:
        logger.exception("Warmup failed")

async def _periodic_refresh():
    interval = max(CACHE_EXPIRATION_TIME - 60, 60)
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.wait_for(refresh_rates(force=True), timeout=30.0)
            logger.info("Periodic rate refresh completed")
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            logger.warning("Periodic rate refresh timed out")
        except Exception:
            logger.exception("Periodic rate refresh failed")

async def on_startup():
    await setup_telegram_logging(bot)
    session = ClientSession(
        timeout=ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT),
        json_serialize=ujson.dumps
    )
    set_http_session(session)
    
    await user_data.init_db()
    
    _bg_tasks.append(_safe_bg_task(_warmup_rates(), name="warmup_rates"))
    _bg_tasks.append(_safe_bg_task(_periodic_refresh(), name="periodic_refresh"))

async def on_shutdown():
    for task in _bg_tasks:
        task.cancel()
    for task in _bg_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _bg_tasks.clear()
    try:
        await close_http_session()
    except Exception:
        logger.exception("Error during HTTP session shutdown")
    try:
        await user_data.close()
    except Exception:
        logger.exception("Error closing database connection")

async def main():
    loop = asyncio.get_event_loop()

    def handle_shutdown_signal():
        logger.info("Received shutdown signal, initiating graceful shutdown...")
        _shutdown_event.set()
        asyncio.create_task(dp.stop_polling())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_shutdown_signal)
        except NotImplementedError:
            pass

    dp.message.middleware(ErrorBoundaryMiddleware())
    dp.message.middleware(RetryMiddleware())
    dp.message.middleware(RateLimitMiddleware(limit=5, window=3.0))

    dp.callback_query.middleware(ErrorBoundaryMiddleware())
    dp.callback_query.middleware(RetryMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware(limit=8, window=3.0))

    dp.inline_query.middleware(ErrorBoundaryMiddleware())
    dp.inline_query.middleware(RetryMiddleware())
    dp.inline_query.middleware(RateLimitMiddleware(limit=5, window=3.0))

    dp.include_router(general.router)
    dp.include_router(admin.router)
    dp.include_router(settings.router)
    dp.include_router(conversion.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")