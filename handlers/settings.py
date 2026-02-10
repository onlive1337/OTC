from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from config.languages import LANGUAGES
from loader import user_data
from utils.keyboards import build_settings_kb, format_settings_text

from data.chat_settings import (
    show_chat_settings, save_chat_settings, show_chat_currencies, 
    show_chat_crypto, toggle_chat_crypto, toggle_chat_currency, 
    back_to_chat_settings
)
from data.user_settings import (
    show_currencies, show_crypto, toggle_crypto, toggle_currency, 
    toggle_quote_format, change_language, set_language
)
from utils.utils import save_settings

router = Router()

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_lang = await user_data.get_user_language(user_id)

    if message.chat.type == 'private':
        use_quote = await user_data.get_user_quote_format(user_id)
        kb = build_settings_kb(user_lang)
        await message.answer(format_settings_text(user_lang, use_quote), reply_markup=kb.as_markup())
    else:
        chat_member = await message.chat.get_member(user_id)
        if chat_member.status in ['creator', 'administrator']:
            use_quote = await user_data.get_chat_quote_format(chat_id)
            kb = build_settings_kb(user_lang, is_chat=True, chat_id=chat_id)
            await message.answer(format_settings_text(user_lang, use_quote, is_chat=True), reply_markup=kb.as_markup())
        else:
            await message.answer(LANGUAGES[user_lang]['admin_only'])

@router.callback_query(F.data == "settings")
async def process_settings(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_lang = await user_data.get_user_language(user_id)
    use_quote = await user_data.get_user_quote_format(user_id)
    
    kb = build_settings_kb(user_lang)
    await callback_query.message.edit_text(
        format_settings_text(user_lang, use_quote), reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    user_id = callback_query.from_user.id
    user_lang = await user_data.get_user_language(user_id)
    use_quote = await user_data.get_user_quote_format(user_id)
    
    kb = build_settings_kb(user_lang)
    await callback_query.message.edit_text(
        format_settings_text(user_lang, use_quote), reply_markup=kb.as_markup()
    )

router.callback_query.register(show_currencies, F.data.startswith("show_currencies_"))
router.callback_query.register(show_crypto, F.data == "show_crypto")
router.callback_query.register(toggle_currency, F.data.startswith("toggle_currency_"))
router.callback_query.register(toggle_crypto, F.data.startswith("toggle_crypto_"))
router.callback_query.register(save_settings, F.data == "save_settings")
router.callback_query.register(change_language, F.data == "change_language")
router.callback_query.register(set_language, F.data.startswith("set_language_"))
router.callback_query.register(toggle_quote_format, F.data == "toggle_quote_format")

router.callback_query.register(show_chat_currencies, F.data.startswith("show_chat_currencies_"))
router.callback_query.register(show_chat_crypto, F.data.startswith("show_chat_crypto_"))
router.callback_query.register(toggle_chat_currency, F.data.startswith("toggle_chat_currency_"))
router.callback_query.register(toggle_chat_crypto, F.data.startswith("toggle_chat_crypto_"))
router.callback_query.register(save_chat_settings, F.data.startswith("save_chat_settings_"))
router.callback_query.register(back_to_chat_settings, F.data.startswith("back_to_chat_settings_"))
