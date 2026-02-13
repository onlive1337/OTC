import asyncio
import sys

if sys.platform != 'win32':
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
import ujson

from config.config import BOT_TOKEN
from data import user_data

session = AiohttpSession(
    json_loads=ujson.loads,
    json_dumps=ujson.dumps,
)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
user_data = user_data.UserData()
