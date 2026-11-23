from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import ujson

from config.config import BOT_TOKEN
from data import user_data
from utils.middleware import TelegramRetryMiddleware

session = AiohttpSession(
    json_dumps=ujson.dumps,
)
session.middleware(TelegramRetryMiddleware())
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
user_data = user_data.UserData()
