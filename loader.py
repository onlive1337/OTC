from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
import ujson

from config.config import BOT_TOKEN
from data import user_data
from utils.middleware import TelegramRetryMiddleware

session = AiohttpSession(
    json_loads=ujson.loads,
    json_dumps=ujson.dumps,
)
session.middleware(TelegramRetryMiddleware())
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode="HTML"),
)
dp = Dispatcher()
user_data = user_data.UserData()
