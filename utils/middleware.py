import time
import logging
import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

logger = logging.getLogger(__name__)

_metrics = {
    "start_time": datetime.now(),
    "total_requests": 0,
    "total_errors": 0,
}

def get_metrics() -> Dict[str, Any]:
    uptime = datetime.now() - _metrics["start_time"]
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "total_requests": _metrics["total_requests"],
        "total_errors": _metrics["total_errors"],
    }


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 5, window: float = 3.0):
        self.limit = limit
        self.window = window
        self._user_timestamps: Dict[int, list] = defaultdict(list)
        self._cleanup_counter = 0
        self._cleanup_interval = 1000

    def _cleanup(self):
        now = time.monotonic()
        to_remove = []
        for uid, timestamps in self._user_timestamps.items():
            timestamps[:] = [t for t in timestamps if now - t < self.window]
            if not timestamps:
                to_remove.append(uid)
        
        for uid in to_remove:
            del self._user_timestamps[uid]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        
        self._cleanup_counter += 1
        if self._cleanup_counter >= self._cleanup_interval:
            self._cleanup()
            self._cleanup_counter = 0
            
        if user is None:
            return await handler(event, data)

        uid = user.id
        now = time.monotonic()
        timestamps = self._user_timestamps[uid]

        timestamps[:] = [t for t in timestamps if now - t < self.window]

        if not timestamps:
            del self._user_timestamps[uid]
            timestamps = self._user_timestamps[uid]

        if len(timestamps) >= self.limit:
            logger.warning("Rate limit hit for user %s", uid)
            return None

        timestamps.append(now)
        return await handler(event, data)


class RetryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramRetryAfter as e:
            logger.warning("Telegram flood control, retrying after %ss", e.retry_after)
            await asyncio.sleep(e.retry_after)
            return await handler(event, data)
        except TelegramAPIError as e:
            logger.error("Telegram API error: %s", e)
            return None


class ErrorBoundaryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        _metrics["total_requests"] += 1
        try:
            return await handler(event, data)
        except (TelegramRetryAfter, TelegramAPIError):
            raise
        except Exception as e:
            _metrics["total_errors"] += 1
            logger.exception("Unhandled error in handler: %s", e)

            try:
                if isinstance(event, Message) and event.chat:
                    user = data.get("event_from_user")
                    if user:
                        from loader import user_data
                        user_lang = await user_data.get_user_language(user.id)
                    else:
                        user_lang = 'en'
                    from config.languages import LANGUAGES
                    await event.answer(LANGUAGES[user_lang].get('error', '⚠️ Error'))
            except Exception:
                pass

            return None
