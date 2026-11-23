import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config.languages import LANGUAGES
from handlers.chat_settings import (
    back_to_chat_settings,
    change_chat_display_format,
    change_chat_language,
    save_chat_settings,
    set_chat_display_format,
    set_chat_language,
    show_chat_crypto,
    show_chat_currencies,
    toggle_chat_crypto,
    toggle_chat_currency,
)
from handlers.user_settings import (
    change_display_format,
    change_language,
    set_display_format,
    set_language,
    show_crypto,
    show_currencies,
    toggle_crypto,
    toggle_currency,
)
from loader import user_data
from utils.callbacks import (
    ChatCurrenciesCB,
    ChatFormatCB,
    ChatLangCB,
    ChatSettingsActionCB,
    ChatToggleCryptoCB,
    ChatToggleCurrencyCB,
    UserCurrenciesCB,
    UserFormatCB,
    UserLangCB,
    UserToggleCryptoCB,
    UserToggleCurrencyCB,
)
from utils.keyboards import build_settings_kb, format_settings_text
from utils.utils import reply_ephemeral_or_fallback, safe_edit_text, save_settings

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    from_user = message.from_user
    if from_user is None:
        return

    user_id = from_user.id
    chat_id = message.chat.id

    if message.chat.type == ChatType.PRIVATE:
        user_lang = await user_data.get_user_language(user_id)
        display_format = await user_data.get_user_display_format(user_id)
        kb = build_settings_kb(user_lang)
        await message.answer(
            format_settings_text(user_lang, display_format),
            reply_markup=kb.as_markup(),
        )
    else:
        chat_member = await message.chat.get_member(user_id)
        if chat_member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
            chat_lang = await user_data.get_chat_language(chat_id)
            display_format = await user_data.get_chat_display_format(chat_id)
            kb = build_settings_kb(chat_lang, is_chat=True, chat_id=chat_id)
            await reply_ephemeral_or_fallback(
                message,
                format_settings_text(chat_lang, display_format, is_chat=True),
                reply_markup=kb.as_markup(),
            )
        else:
            chat_lang = await user_data.get_chat_language(chat_id)
            await reply_ephemeral_or_fallback(message, LANGUAGES[chat_lang]['admin_only'])


@router.callback_query(F.data == "settings")
async def process_settings(callback_query: CallbackQuery):
    await callback_query.answer()
    if not isinstance(callback_query.message, Message):
        return

    from_user = callback_query.from_user
    if from_user is None:
        return

    user_id = from_user.id
    user_lang = await user_data.get_user_language(user_id)
    display_format = await user_data.get_user_display_format(user_id)

    kb = build_settings_kb(user_lang)
    await safe_edit_text(
        callback_query.message,
        format_settings_text(user_lang, display_format),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback_query: CallbackQuery):
    await callback_query.answer()
    if not isinstance(callback_query.message, Message):
        return

    from_user = callback_query.from_user
    if from_user is None:
        return

    await user_data.update_user_data(from_user.id)
    user_id = from_user.id
    user_lang = await user_data.get_user_language(user_id)
    display_format = await user_data.get_user_display_format(user_id)

    kb = build_settings_kb(user_lang)
    await safe_edit_text(
        callback_query.message,
        format_settings_text(user_lang, display_format),
        reply_markup=kb.as_markup(),
    )


router.callback_query.register(show_currencies, UserCurrenciesCB.filter())
router.callback_query.register(show_crypto, F.data == "show_crypto")
router.callback_query.register(toggle_currency, UserToggleCurrencyCB.filter())
router.callback_query.register(toggle_crypto, UserToggleCryptoCB.filter())
router.callback_query.register(save_settings, F.data == "save_settings")
router.callback_query.register(change_language, F.data == "change_language")
router.callback_query.register(set_language, UserLangCB.filter())
router.callback_query.register(change_display_format, F.data == "change_display_format")
router.callback_query.register(set_display_format, UserFormatCB.filter())

router.callback_query.register(show_chat_currencies, ChatCurrenciesCB.filter())
router.callback_query.register(show_chat_crypto, ChatSettingsActionCB.filter(F.action == "crypto"))
router.callback_query.register(toggle_chat_currency, ChatToggleCurrencyCB.filter())
router.callback_query.register(toggle_chat_crypto, ChatToggleCryptoCB.filter())
router.callback_query.register(save_chat_settings, ChatSettingsActionCB.filter(F.action == "save"))
router.callback_query.register(back_to_chat_settings, ChatSettingsActionCB.filter(F.action == "back"))
router.callback_query.register(change_chat_language, ChatSettingsActionCB.filter(F.action == "lang"))
router.callback_query.register(set_chat_language, ChatLangCB.filter())
router.callback_query.register(change_chat_display_format, ChatSettingsActionCB.filter(F.action == "format"))
router.callback_query.register(set_chat_display_format, ChatFormatCB.filter())
