import logging
import traceback
import html
from aiogram import Bot
from config.config import LOG_CHAT_ID
import asyncio
import time
from collections import deque

MAX_TELEGRAM_LOG_LEN = 3800
MIN_INTERVAL_SEC = 5
MAX_BUFFER_SIZE = 10
_last_sent = 0.0
_log_buffer: deque = deque(maxlen=MAX_BUFFER_SIZE)
_buffer_lock = asyncio.Lock()

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot
        self._flush_task = None

    def emit(self, record):
        global _last_sent
        if not LOG_CHAT_ID:
            return

        log_entry = self.format_error(record)
        _log_buffer.append(log_entry)

        now = time.time()
        if now - _last_sent < MIN_INTERVAL_SEC:
            if self._flush_task is None or self._flush_task.done():
                delay = MIN_INTERVAL_SEC - (now - _last_sent) + 0.1
                self._flush_task = asyncio.create_task(self._delayed_flush(delay))
            return

        _last_sent = now
        task = asyncio.create_task(self._flush_buffer())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _delayed_flush(self, delay: float):
        global _last_sent
        await asyncio.sleep(delay)
        _last_sent = time.time()
        await self._flush_buffer()

    async def _flush_buffer(self):
        if not _log_buffer:
            return

        messages = list(_log_buffer)
        _log_buffer.clear()

        combined = "\n\n---\n\n".join(messages)
        if len(combined) > MAX_TELEGRAM_LOG_LEN:
            combined = combined[:MAX_TELEGRAM_LOG_LEN] + "...\n\n[truncated]"

        await self.send_log_to_telegram(combined)

    def format_error(self, record):
        base = f"{record.levelname} [{record.name}]: {record.getMessage()}"
        if record.exc_info:
            tb_list = traceback.format_exception(*record.exc_info)
            tb_str = "".join(tb_list)
            base += f"\n\nTraceback:\n{tb_str}"
        if len(base) > MAX_TELEGRAM_LOG_LEN:
            base = base[:MAX_TELEGRAM_LOG_LEN] + '...'
        return base

    async def send_log_to_telegram(self, log_entry):
        try:
            safe_entry = html.escape(log_entry)
            await self.bot.send_message(LOG_CHAT_ID, safe_entry)
        except Exception as e:
            print(f"Failed to send log to Telegram: {e}")

async def setup_telegram_logging(bot: Bot):
    if not LOG_CHAT_ID:
        logging.getLogger(__name__).info("LOG_CHAT_ID not set, Telegram logging disabled")
        return
    telegram_handler = TelegramLogHandler(bot)
    telegram_handler.setLevel(logging.ERROR)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(telegram_handler)