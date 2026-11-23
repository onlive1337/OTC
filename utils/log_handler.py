import asyncio
from collections import deque
import html
import logging
import sys
import time
import traceback
from typing import Coroutine, Optional

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config.config import LOG_CHAT_ID

MAX_TELEGRAM_LOG_LEN = 3800
MIN_INTERVAL_SEC = 5
MAX_BUFFER_SIZE = 50

_telegram_handler: Optional["TelegramLogHandler"] = None


class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot, chat_id: Optional[int | str] = None):
        super().__init__()
        self.bot = bot
        self._chat_id = chat_id
        self._last_sent = 0.0
        self._dropped_count = 0
        self._log_buffer: deque[str] = deque(maxlen=MAX_BUFFER_SIZE)
        self._buffer_lock: Optional[asyncio.Lock] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._pending_tasks: set[asyncio.Task] = set()

    def _target_chat_id(self) -> Optional[int | str]:
        return self._chat_id if self._chat_id is not None else LOG_CHAT_ID

    def _get_lock(self) -> asyncio.Lock:
        if self._buffer_lock is None:
            self._buffer_lock = asyncio.Lock()
        return self._buffer_lock

    def _spawn_task(self, coro: Coroutine, *, name: str) -> Optional[asyncio.Task]:
        try:
            task = asyncio.create_task(coro, name=name)
        except RuntimeError:
            coro.close()
            return None

        self._pending_tasks.add(task)

        def _on_done(t: asyncio.Task) -> None:
            self._pending_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                print(f"Telegram log task '{name}' failed: {exc}", file=sys.stderr)

        task.add_done_callback(_on_done)
        return task

    def emit(self, record):
        if not self._target_chat_id():
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        if len(self._log_buffer) >= MAX_BUFFER_SIZE:
            self._dropped_count += 1

        log_entry = self.format_error(record)
        self._log_buffer.append(log_entry)

        now = time.time()
        if now - self._last_sent < MIN_INTERVAL_SEC:
            if self._flush_task is None or self._flush_task.done():
                delay = MIN_INTERVAL_SEC - (now - self._last_sent) + 0.1
                self._flush_task = self._spawn_task(
                    self._delayed_flush(delay),
                    name="telegram_log_delayed_flush",
                )
            return

        self._last_sent = now
        self._spawn_task(self._flush_buffer(), name="telegram_log_flush")

    async def _delayed_flush(self, delay: float):
        await asyncio.sleep(delay)
        self._last_sent = time.time()
        await self._flush_buffer()

    async def _flush_buffer(self):
        async with self._get_lock():
            if not self._log_buffer:
                return

            messages = list(self._log_buffer)
            self._log_buffer.clear()
            dropped = self._dropped_count
            self._dropped_count = 0

        combined = "\n\n---\n\n".join(messages)
        if dropped:
            combined = f"⚠️ {dropped} log message(s) dropped due to rate limiting\n\n" + combined
        if len(combined) > MAX_TELEGRAM_LOG_LEN:
            combined = combined[:MAX_TELEGRAM_LOG_LEN] + "...\n\n[truncated]"

        await self.send_log_to_telegram(combined)

    @staticmethod
    def format_error(record):
        base = f"{record.levelname} [{record.name}]: {record.getMessage()}"
        if record.exc_info:
            tb_list = traceback.format_exception(*record.exc_info)
            tb_str = "".join(tb_list)
            base += f"\n\nTraceback:\n{tb_str}"
        if len(base) > MAX_TELEGRAM_LOG_LEN:
            base = base[:MAX_TELEGRAM_LOG_LEN] + '...'
        return base

    async def send_log_to_telegram(self, log_entry: str):
        chat_id = self._target_chat_id()
        if not chat_id:
            return
        try:
            safe_entry = html.escape(str(log_entry))
            await self.bot.send_message(chat_id, safe_entry)
        except (TelegramAPIError, aiohttp.ClientError, asyncio.TimeoutError, OSError, RuntimeError) as e:
            print(f"Failed to send log to Telegram: {e}", file=sys.stderr)

    async def close(self):
        flush_task = self._flush_task
        self._flush_task = None
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
            await asyncio.gather(flush_task, return_exceptions=True)

        pending = [t for t in self._pending_tasks if not t.done()]
        if pending:
            _done, still_running = await asyncio.wait(pending, timeout=2.0)
            for task in still_running:
                task.cancel()
            if still_running:
                await asyncio.gather(*still_running, return_exceptions=True)

        await self._flush_buffer()
        self._pending_tasks.clear()


async def setup_telegram_logging(bot: Bot) -> Optional[TelegramLogHandler]:
    global _telegram_handler
    if not LOG_CHAT_ID:
        logging.getLogger(__name__).info("LOG_CHAT_ID not set, Telegram logging disabled")
        return None

    if _telegram_handler is not None:
        await close_telegram_logging()

    telegram_handler = TelegramLogHandler(bot)
    telegram_handler.setLevel(logging.ERROR)

    root_logger = logging.getLogger()
    root_logger.addHandler(telegram_handler)
    _telegram_handler = telegram_handler
    return telegram_handler


async def close_telegram_logging():
    global _telegram_handler
    handler = _telegram_handler
    _telegram_handler = None
    if handler is None:
        return

    logging.getLogger().removeHandler(handler)
    await handler.close()
