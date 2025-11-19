from aiogram import Bot, Dispatcher
from config.config import BOT_TOKEN
from data import user_data

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_data = user_data.UserData()
