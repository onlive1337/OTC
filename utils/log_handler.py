import logging
from aiogram import Bot
from config.config import LOG_CHAT_ID
import asyncio
import time

MAX_TELEGRAM_LOG_LEN = 3800
MIN_INTERVAL_SEC = 5
_last_sent = 0.0

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot

    def emit(self, record):
        global _last_sent
        now = time.time()
        if now - _last_sent < MIN_INTERVAL_SEC:
            return
        _last_sent = now
        log_entry = self.format_error(record)
        asyncio.create_task(self.send_log_to_telegram(log_entry))

    def format_error(self, record):
        base = f"{record.levelname} [{record.name}]: {record.getMessage()}"
        if record.exc_info:
            base += f"\n\nError: {str(record.exc_info[1])}"
        if len(base) > MAX_TELEGRAM_LOG_LEN:
            base = base[:MAX_TELEGRAM_LOG_LEN] + '...'
        return base

    async def send_log_to_telegram(self, log_entry):
        try:
            await self.bot.send_message(LOG_CHAT_ID, log_entry)
        except Exception as e:
            print(f"Failed to send log to Telegram: {e}")

async def setup_telegram_logging(bot: Bot):
    telegram_handler = TelegramLogHandler(bot)
    telegram_handler.setLevel(logging.ERROR)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(telegram_handler)