from collections.abc import Collection

from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from utils.button_styles import EMOJI, disabled_button, primary_button, success_button
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
from utils.formatter import (
    DISPLAY_FORMATS,
    FORMAT_PLAIN,
    FORMAT_QUOTE,
    FORMAT_TABLE,
    get_currency_symbol,
)

_FORMAT_KEYS = {
    FORMAT_PLAIN: 'format_plain',
    FORMAT_QUOTE: 'format_quote',
    FORMAT_TABLE: 'format_table',
}


def build_user_settings_kb(user_lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button(LANGUAGES[user_lang]['currencies'], UserCurrenciesCB(page=0).pack(), emoji=EMOJI['currencies']),
        primary_button(LANGUAGES[user_lang]['cryptocurrencies'], "show_crypto", emoji=EMOJI['crypto']),
    )
    kb.row(
        primary_button(LANGUAGES[user_lang]['language'], "change_language", emoji=EMOJI['language']),
        primary_button(LANGUAGES[user_lang]['display_format_button'], "change_display_format", emoji=EMOJI['quote_format']),
    )
    kb.row(success_button(LANGUAGES[user_lang]['save_button'], "save_settings", emoji=EMOJI['save']))
    kb.row(primary_button(LANGUAGES[user_lang]['back'], "back_to_main", emoji=EMOJI['back']))
    return kb


def build_chat_settings_kb(user_lang: str, chat_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button(
            LANGUAGES[user_lang]['currencies'],
            ChatCurrenciesCB(chat_id=chat_id, page=0).pack(),
            emoji=EMOJI['currencies'],
        ),
        primary_button(
            LANGUAGES[user_lang]['cryptocurrencies'],
            ChatSettingsActionCB(chat_id=chat_id, action="crypto").pack(),
            emoji=EMOJI['crypto'],
        ),
    )
    kb.row(
        primary_button(
            LANGUAGES[user_lang]['language'],
            ChatSettingsActionCB(chat_id=chat_id, action="lang").pack(),
            emoji=EMOJI['language'],
        ),
        primary_button(
            LANGUAGES[user_lang]['display_format_button'],
            ChatSettingsActionCB(chat_id=chat_id, action="format").pack(),
            emoji=EMOJI['quote_format'],
        ),
    )
    kb.row(
        success_button(
            LANGUAGES[user_lang]['save_button'],
            ChatSettingsActionCB(chat_id=chat_id, action="save").pack(),
            emoji=EMOJI['save'],
        )
    )
    return kb


def build_settings_kb(user_lang: str, is_chat: bool = False, chat_id: int | None = None) -> InlineKeyboardBuilder:
    if is_chat:
        if chat_id is None:
            raise ValueError("chat_id is required when is_chat=True")
        return build_chat_settings_kb(user_lang, chat_id)
    return build_user_settings_kb(user_lang)


def _settings_back_callback(chat_id: int | None) -> str:
    if chat_id is not None:
        return ChatSettingsActionCB(chat_id=chat_id, action="back").pack()
    return "back_to_settings"


def build_back_to_settings_kb(user_lang: str, *, chat_id: int | None = None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button(
            LANGUAGES[user_lang]['back_to_settings'],
            _settings_back_callback(chat_id),
            emoji=EMOJI['back'],
        )
    )
    return kb


def build_currencies_page_kb(
    user_lang: str,
    selected_currencies: Collection[str],
    page: int,
    *,
    chat_id: int | None = None,
    currencies_per_page: int = 5,
) -> InlineKeyboardBuilder:
    total_pages = max(1, (len(ACTIVE_CURRENCIES) + currencies_per_page - 1) // currencies_per_page)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * currencies_per_page
    end = start + currencies_per_page

    kb = InlineKeyboardBuilder()
    for currency in ACTIVE_CURRENCIES[start:end]:
        status = "✅" if currency in selected_currencies else "❌"
        toggle_cb = (
            ChatToggleCurrencyCB(chat_id=chat_id, currency=currency, page=safe_page).pack()
            if chat_id is not None
            else UserToggleCurrencyCB(currency=currency, page=safe_page).pack()
        )
        kb.row(primary_button(f"{get_currency_symbol(currency)}{currency} {status}", toggle_cb))

    nav_buttons = []
    if safe_page > 0:
        prev_cb = (
            ChatCurrenciesCB(chat_id=chat_id, page=safe_page - 1).pack()
            if chat_id is not None
            else UserCurrenciesCB(page=safe_page - 1).pack()
        )
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['back'], prev_cb, emoji=EMOJI['back']))

    nav_buttons.append(disabled_button(f"{safe_page + 1} / {total_pages}"))

    if end < len(ACTIVE_CURRENCIES):
        next_cb = (
            ChatCurrenciesCB(chat_id=chat_id, page=safe_page + 1).pack()
            if chat_id is not None
            else UserCurrenciesCB(page=safe_page + 1).pack()
        )
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['forward'], next_cb, emoji=EMOJI['forward']))

    kb.row(*nav_buttons)
    kb.row(
        primary_button(
            LANGUAGES[user_lang]['back_to_settings'],
            _settings_back_callback(chat_id),
            emoji=EMOJI['settings'],
        )
    )
    return kb


def build_crypto_kb(
    user_lang: str,
    selected_crypto: Collection[str],
    *,
    chat_id: int | None = None,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in selected_crypto else "❌"
        toggle_cb = (
            ChatToggleCryptoCB(chat_id=chat_id, symbol=crypto).pack()
            if chat_id is not None
            else UserToggleCryptoCB(symbol=crypto).pack()
        )
        kb.row(primary_button(f"{get_currency_symbol(crypto)}{crypto} {status}", toggle_cb))

    kb.row(
        primary_button(
            LANGUAGES[user_lang]['back_to_settings'],
            _settings_back_callback(chat_id),
            emoji=EMOJI['settings'],
        )
    )
    pair_rows = [2] * (len(CRYPTO_CURRENCIES) // 2)
    remainder = [1] if len(CRYPTO_CURRENCIES) % 2 else []
    kb.adjust(*pair_rows, *remainder, 1)
    return kb


def build_language_kb(user_lang: str, *, chat_id: int | None = None) -> InlineKeyboardBuilder:
    ru_cb = ChatLangCB(chat_id=chat_id, lang="ru").pack() if chat_id is not None else UserLangCB(lang="ru").pack()
    en_cb = ChatLangCB(chat_id=chat_id, lang="en").pack() if chat_id is not None else UserLangCB(lang="en").pack()

    kb = InlineKeyboardBuilder()
    kb.row(primary_button("Русский", ru_cb), primary_button("English", en_cb))
    kb.row(
        primary_button(
            LANGUAGES[user_lang]['back_to_settings'],
            _settings_back_callback(chat_id),
            emoji=EMOJI['back'],
        )
    )
    return kb


def build_display_format_kb(
    user_lang: str,
    current_format: str,
    *,
    chat_id: int | None = None,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for fmt in DISPLAY_FORMATS:
        label = LANGUAGES[user_lang][_FORMAT_KEYS[fmt]]
        suffix = " ✅" if fmt == current_format else ""
        cb = ChatFormatCB(chat_id=chat_id, fmt=fmt).pack() if chat_id is not None else UserFormatCB(fmt=fmt).pack()
        kb.row(primary_button(f"{label}{suffix}", cb))

    kb.row(
        primary_button(
            LANGUAGES[user_lang]['back_to_settings'],
            _settings_back_callback(chat_id),
            emoji=EMOJI['back'],
        )
    )
    return kb


def format_settings_text(
    user_lang: str,
    display_format: str,
    is_chat: bool = False,
) -> str:
    title = LANGUAGES[user_lang]['chat_settings'] if is_chat else LANGUAGES[user_lang]['settings']
    fmt_label = LANGUAGES[user_lang][_FORMAT_KEYS.get(display_format, 'format_quote')]
    return (
        f"{title}\n\n"
        f"{LANGUAGES[user_lang]['display_format_status']}: {fmt_label}"
    )
