import logging
from aiogram import Bot
from config.config import LOG_CHAT_ID
import asyncio

class TelegramLogHandler(logging.Handler):
    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot

    def emit(self, record):
        log_entry = self.format_error(record)
        asyncio.create_task(self.send_log_to_telegram(log_entry))

    def format_error(self, record):
        if record.exc_info:
            return f"{record.levelname}: {record.getMessage()}\n\nError: {str(record.exc_info[1])}"
        return f"{record.levelname}: {record.getMessage()}"

    async def send_log_to_telegram(self, log_entry):
        try:
            if len(log_entry) > 4000:
                log_entry = log_entry[:3997] + "..."
            await self.bot.send_message(LOG_CHAT_ID, log_entry)
        except Exception as e:
            print(f"Failed to send log to Telegram: {e}")

async def setup_telegram_logging(bot: Bot):
    telegram_handler = TelegramLogHandler(bot)
    telegram_handler.setLevel(logging.ERROR)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(telegram_handler)