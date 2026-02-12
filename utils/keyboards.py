from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.languages import LANGUAGES
from utils.button_styles import primary_button, success_button, EMOJI


def build_user_settings_kb(user_lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button(LANGUAGES[user_lang]['currencies'], "show_currencies_0", emoji=EMOJI['currencies']),
        primary_button(LANGUAGES[user_lang]['cryptocurrencies'], "show_crypto", emoji=EMOJI['crypto'])
    )
    kb.row(
        primary_button(LANGUAGES[user_lang]['language'], "change_language", emoji=EMOJI['language']),
        primary_button(LANGUAGES[user_lang]['quote_format'], "toggle_quote_format", emoji=EMOJI['quote_format'])
    )
    kb.row(success_button(LANGUAGES[user_lang]['save_button'], "save_settings", emoji=EMOJI['save']))
    kb.row(primary_button(LANGUAGES[user_lang]['back'], "back_to_main", emoji=EMOJI['back']))
    return kb


def build_chat_settings_kb(user_lang: str, chat_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button(LANGUAGES[user_lang]['currencies'], f"show_chat_currencies_{chat_id}_0", emoji=EMOJI['currencies']),
        primary_button(LANGUAGES[user_lang]['cryptocurrencies'], f"show_chat_crypto_{chat_id}", emoji=EMOJI['crypto'])
    )
    kb.row(primary_button(LANGUAGES[user_lang]['quote_format'], f"toggle_chat_quote_format_{chat_id}", emoji=EMOJI['quote_format']))
    kb.row(primary_button(LANGUAGES[user_lang]['language'], f"change_chat_language_{chat_id}", emoji=EMOJI['language']))
    kb.row(success_button(LANGUAGES[user_lang]['save_button'], f"save_chat_settings_{chat_id}", emoji=EMOJI['save']))
    return kb


def build_settings_kb(user_lang: str, is_chat: bool = False, chat_id: int = None) -> InlineKeyboardBuilder:
    if is_chat:
        return build_chat_settings_kb(user_lang, chat_id)
    return build_user_settings_kb(user_lang)


def format_settings_text(user_lang: str, use_quote: bool, is_chat: bool = False) -> str:
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    title = LANGUAGES[user_lang]['chat_settings'] if is_chat else LANGUAGES[user_lang]['settings']
    return f"{title}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
