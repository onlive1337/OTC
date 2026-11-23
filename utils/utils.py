import logging
from typing import Any, Union

from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, EphemeralMessageParameters, Message

from config.languages import LANGUAGES
from loader import user_data

logger = logging.getLogger(__name__)


async def safe_edit_text(message: Any, text: str, reply_markup=None):
    """Edit regular or ephemeral messages while ignoring unmodified-text errors."""
    if not isinstance(message, Message):
        return
    try:
        if message.ephemeral_message_id is not None:
            await message.edit_ephemeral_text(text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def reply_ephemeral_or_fallback(message: Message, text: str, reply_markup=None):
    """Send an ephemeral reply in groups when permitted, falling back to a normal reply."""
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and message.from_user is not None:
        if message.ephemeral_message_id is not None:
            return await message.reply(text=text, reply_markup=reply_markup)
        try:
            return await message.answer(
                text=text,
                reply_markup=reply_markup,
                ephemeral_message_parameters=EphemeralMessageParameters(
                    receiver_user_id=message.from_user.id,
                ),
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            logger.debug(
                "Ephemeral reply rejected in chat %s, falling back to regular reply",
                message.chat.id,
            )
    return await message.reply(text=text, reply_markup=reply_markup)


async def delete_conversion_message(callback_query: CallbackQuery):
    if isinstance(callback_query.message, Message):
        try:
            if callback_query.message.ephemeral_message_id is not None:
                await callback_query.message.delete_ephemeral()
            else:
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
    await safe_edit_text(callback_query.message, LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()


async def check_admin_rights(message_or_callback: Union[Message, CallbackQuery], user_id: int, chat_id: int) -> bool:
    bot = message_or_callback.bot
    if bot is None:
        return False

    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except TelegramAPIError:
        logger.exception("Error checking admin rights")
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

    if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP) and chat_id:
        lang_code = await user_data.get_chat_language(chat_id)
    else:
        lang_code = await user_data.get_user_language(user_id)

    error_text = LANGUAGES[lang_code].get('not_admin_message', 'You need to be an admin to change these settings.')

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer(error_text, show_alert=True)
    else:
        await reply_ephemeral_or_fallback(message_or_callback, error_text)
