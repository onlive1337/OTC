import logging
from typing import Union

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from config.languages import LANGUAGES
from loader import user_data

logger = logging.getLogger(__name__)


async def delete_conversion_message(callback_query: CallbackQuery):
    if isinstance(callback_query.message, Message):
        try:
            await callback_query.message.delete()
        except TelegramAPIError:
            pass
    try:
        await callback_query.answer()
    except TelegramAPIError:
        pass

async def save_settings(callback_query: CallbackQuery):
    if not isinstance(callback_query.message, Message):
        await callback_query.answer()
        return

    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()

async def check_admin_rights(message_or_callback: Union[Message, CallbackQuery], user_id: int, chat_id: int) -> bool:
    bot = message_or_callback.bot
    if bot is None:
        return False

    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except TelegramAPIError as e:
        logger.error(f"Error checking admin rights: {e}")
        return False

async def show_not_admin_message(message_or_callback: Union[Message, CallbackQuery], user_id: int):
    chat_id = None
    chat_type = None
    
    if isinstance(message_or_callback, Message):
        chat_id = message_or_callback.chat.id
        chat_type = message_or_callback.chat.type
    elif isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        chat_id = message_or_callback.message.chat.id
        chat_type = message_or_callback.message.chat.type

    if chat_type in ('group', 'supergroup') and chat_id:
        lang_code = await user_data.get_chat_language(chat_id)
    else:
        lang_code = await user_data.get_user_language(user_id)

    error_text = LANGUAGES[lang_code].get('not_admin_message', 'You need to be an admin to change these settings.')
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer(error_text, show_alert=True)
    else:
        await message_or_callback.reply(error_text)