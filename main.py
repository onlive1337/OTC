import asyncio
import logging
from aiohttp import ClientSession, ClientTimeout

from config.config import LOG_LEVEL, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT
from loader import bot, dp, user_data
from utils.utils import get_exchange_rates, set_http_session, close_http_session
from utils.log_handler import setup_telegram_logging

from utils.middleware import RateLimitMiddleware, RetryMiddleware, ErrorBoundaryMiddleware

from handlers import general, admin, settings, conversion

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s %(levelname)s [%(name)s]: %(message)s'
)
logger = logging.getLogger(__name__)

def _safe_task(coro, name: str = "background"):
    task = asyncio.create_task(coro, name=name)
    def _on_done(t: asyncio.Task):
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"Background task '{name}' failed: {exc}", exc_info=exc)
    task.add_done_callback(_on_done)
    return task

async def _warmup_rates():
    try:
        await get_exchange_rates()
        logger.info("Rates cache warmed up")
    except Exception:
        logger.exception("Warmup failed")

async def on_startup():
    await setup_telegram_logging(bot)
    session = ClientSession(timeout=ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT))
    set_http_session(session)
    
    await user_data.init_db()
    
    _safe_task(_warmup_rates(), name="warmup_rates")

async def on_shutdown():
    try:
        await close_http_session()
    except Exception:
        logger.exception("Error during HTTP session shutdown")
    try:
        await user_data.close()
    except Exception:
        logger.exception("Error closing database connection")

async def main():
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