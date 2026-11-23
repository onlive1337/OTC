import logging
import re
import sqlite3
from typing import List, Tuple

from aiogram import Bot, Router, types
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import (
    ALL_CURRENCIES,
    CRYPTO_CURRENCIES,
    MAX_CONVERSION_AMOUNT,
    MIN_CONVERSION_AMOUNT,
)
from config.languages import LANGUAGES
from loader import user_data
from utils.button_styles import EMOJI, danger_button, primary_button
from utils.formatter import (
    FORMAT_QUOTE,
    FORMAT_TABLE,
    build_conversion_rich_message,
    build_math_response,
    build_multi_conversion_rich_message,
    build_rich_rows,
    format_large_number,
    format_too_large_message,
    format_too_small_message,
    get_currency_symbol,
    resolve_display_format,
)
from utils.parser import (
    PATTERN_TO_CODE,
    URL_OR_QUERY_TEXT_REGEX,
    contains_known_currency,
    detect_amount_bounds_from_text,
    extract_unknown_currency,
    find_similar_currencies,
    find_target_currency,
    is_math_expression,
    parse_amount_and_currency,
    parse_mathematical_expression,
)
from utils.rates import convert_currency, get_exchange_rates
from utils.utils import reply_ephemeral_or_fallback

logger = logging.getLogger(__name__)
router = Router()

_SEPARATORS = [
    r'\s+и\s+', r'\s+and\s+', r'\s+а\s+также\s+',
    r';', r'\n', r',\s+(?=\d)', r'\s+\+\s+'
]
_SEPARATORS_REGEX = re.compile(f"({'|'.join(_SEPARATORS)})", re.IGNORECASE)


async def _validate_amount_or_reply(message: types.Message, user_lang: str, amount: float) -> bool:
    if amount <= 0:
        await reply_ephemeral_or_fallback(message, LANGUAGES[user_lang].get('negative_or_zero_amount'))
        return False
    if amount < MIN_CONVERSION_AMOUNT:
        await reply_ephemeral_or_fallback(message, format_too_small_message(user_lang))
        return False
    if amount > MAX_CONVERSION_AMOUNT:
        await reply_ephemeral_or_fallback(message, format_too_large_message(user_lang))
        return False
    return True


async def _get_rates_or_reply(message: types.Message, user_lang: str):
    rates = await get_exchange_rates()
    if not rates:
        await message.answer(LANGUAGES[user_lang]['error'])
        return None
    return rates


async def _resolve_chat_user_prefs(message: types.Message):
    from_user = message.from_user
    if from_user is None:
        return (
            'ru',
            [],
            [],
            False if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) else True,
            False,
            0,
            message.chat.id,
        )

    user_id = from_user.id
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        data = await user_data.get_chat_data(message.chat.id)
        display_format = resolve_display_format(
            data.get('quote_format', False),
            data.get('rich_format', False),
        )
        return (
            data.get('language', 'ru'),
            data.get('currencies', []),
            data.get('crypto', []),
            display_format == FORMAT_QUOTE,
            display_format == FORMAT_TABLE,
            user_id,
            message.chat.id,
        )

    data = await user_data.get_user_data(user_id)
    display_format = resolve_display_format(
        data.get('use_quote_format', True),
        data.get('use_rich_format', False),
    )
    return (
        data.get('language', 'ru'),
        data.get('selected_currencies', []),
        data.get('selected_crypto', []),
        display_format == FORMAT_QUOTE,
        display_format == FORMAT_TABLE,
        user_id,
        message.chat.id,
    )


def _build_delete_conversion_kb(user_lang: str):
    kb = InlineKeyboardBuilder()
    kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', 'Delete'), 'delete_conversion', emoji=EMOJI['delete']))
    return kb


def _format_conversion_lines(
    amount: float,
    from_currency: str,
    targets: List[str],
    rates: dict,
    *,
    is_crypto: bool = False,
) -> List[str]:
    lines = []
    for to_cur in targets:
        if to_cur == from_currency:
            continue
        try:
            converted = convert_currency(amount, from_currency, to_cur, rates)
        except (KeyError, ValueError, OverflowError):
            continue
        lines.append(f"{format_large_number(converted, is_crypto)} {get_currency_symbol(to_cur)}{to_cur}")
    return lines


async def process_targeted_conversion(message: types.Message, amount: float, from_currency: str, to_currency: str):
    user_lang, _, _, _, _, user_id, _ = await _resolve_chat_user_prefs(message)

    try:
        if not await _validate_amount_or_reply(message, user_lang, amount):
            return

        rates = await _get_rates_or_reply(message, user_lang)
        if rates is None:
            return

        converted = convert_currency(amount, from_currency, to_currency, rates)
        is_crypto = to_currency in CRYPTO_CURRENCIES

        response = (
            f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
            f"= {format_large_number(converted, is_crypto)} {get_currency_symbol(to_currency)}{to_currency}"
        )

        kb = _build_delete_conversion_kb(user_lang)
        await message.reply(text=response, reply_markup=kb.as_markup())
    except KeyError:
        await message.answer(LANGUAGES[user_lang]['error'])
    except (ValueError, TypeError, OverflowError, sqlite3.Error):
        logger.exception("Error in targeted conversion for user %s", user_id)
        await message.answer(LANGUAGES[user_lang]['error'])
    except TelegramAPIError as e:
        logger.warning("Failed to send targeted conversion for user %s: %s", user_id, e)


async def process_multiple_conversions(message: types.Message, requests: List[Tuple[float, str]]):
    user_lang, user_currencies, user_crypto, use_quote, use_rich, user_id, _ = await _resolve_chat_user_prefs(message)

    try:
        rates = await _get_rates_or_reply(message, user_lang)
        if rates is None:
            return

        final_response = ""
        skipped_too_large = False
        rich_items = []

        for amount, from_currency in requests:
            if amount <= 0 or amount > MAX_CONVERSION_AMOUNT:
                if amount > MAX_CONVERSION_AMOUNT:
                    skipped_too_large = True
                continue

            response = f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
            conversion_parts = []

            if user_currencies:
                conversion_parts.append(f"{LANGUAGES[user_lang]['fiat_currencies']}")
                fiat_parts = _format_conversion_lines(amount, from_currency, user_currencies, rates)
                if fiat_parts:
                    conversion_parts.append("\n".join(fiat_parts))

            if user_crypto:
                conversion_parts.append(f"{LANGUAGES[user_lang]['cryptocurrencies_output']}")
                crypto_parts = _format_conversion_lines(amount, from_currency, user_crypto, rates, is_crypto=True)
                if crypto_parts:
                    conversion_parts.append("\n".join(crypto_parts))

            content = "\n\n".join(conversion_parts)
            if use_quote:
                response += "<blockquote expandable>" + content + "</blockquote>\n\n"
            else:
                response += content + "\n\n"
            final_response += response

            if use_rich:
                fiat_rows = build_rich_rows(amount, from_currency, user_currencies, rates, False) if user_currencies else []
                crypto_rows = build_rich_rows(amount, from_currency, user_crypto, rates, True) if user_crypto else []
                if fiat_rows or crypto_rows:
                    rich_items.append((amount, from_currency, fiat_rows, crypto_rows))

        if final_response:
            kb = _build_delete_conversion_kb(user_lang)
            if use_rich and rich_items:
                rich_msg = build_multi_conversion_rich_message(rich_items, user_lang, use_quote)
                try:
                    await message.reply_rich(rich_message=rich_msg, reply_markup=kb.as_markup())
                    return
                except TelegramBadRequest:
                    logger.debug("reply_rich rejected in chat %s, falling back to HTML reply", message.chat.id)

            await message.reply(
                text=final_response.strip(),
                reply_markup=kb.as_markup()
            )
        elif skipped_too_large:
            await reply_ephemeral_or_fallback(message, format_too_large_message(user_lang))

    except (KeyError, ValueError, TypeError, OverflowError, sqlite3.Error):
        logger.exception("Error in process_multiple_conversions for user %s", user_id)
        await message.answer(LANGUAGES[user_lang]['error'])
    except TelegramAPIError as e:
        logger.warning("Failed to send multiple conversions for user %s: %s", user_id, e)


async def process_conversion(message: types.Message, amount: float, from_currency: str):
    user_lang, user_currencies, user_crypto, use_quote, use_rich, user_id, _ = await _resolve_chat_user_prefs(message)

    try:
        if not await _validate_amount_or_reply(message, user_lang, amount):
            return

        rates = await _get_rates_or_reply(message, user_lang)
        if rates is None:
            return

        response_parts = [
            f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
        ]

        if user_currencies:
            response_parts.append(f"\n{LANGUAGES[user_lang]['fiat_currencies']}\n")
            fiat_conversions = _format_conversion_lines(amount, from_currency, user_currencies, rates)
            joined_fiat = "\n".join(fiat_conversions)
            response_parts.append(f"<blockquote expandable>{joined_fiat}</blockquote>" if use_quote else joined_fiat)

        if user_crypto:
            response_parts.append(f"\n\n{LANGUAGES[user_lang]['cryptocurrencies_output']}\n")
            crypto_conversions = _format_conversion_lines(amount, from_currency, user_crypto, rates, is_crypto=True)
            joined_crypto = "\n".join(crypto_conversions)
            response_parts.append(f"<blockquote expandable>{joined_crypto}</blockquote>" if use_quote else joined_crypto)

        kb = _build_delete_conversion_kb(user_lang)
        final_response = "".join(response_parts).strip()

        if use_rich:
            fiat_rows = build_rich_rows(amount, from_currency, user_currencies, rates, False) if user_currencies else []
            crypto_rows = build_rich_rows(amount, from_currency, user_crypto, rates, True) if user_crypto else []
            if fiat_rows or crypto_rows:
                rich_msg = build_conversion_rich_message(
                    amount, from_currency, fiat_rows, crypto_rows, user_lang, use_quote
                )
                try:
                    await message.reply_rich(rich_message=rich_msg, reply_markup=kb.as_markup())
                    return
                except TelegramBadRequest:
                    logger.debug("reply_rich rejected in chat %s, falling back to HTML reply", message.chat.id)

        await message.reply(
            text=final_response,
            reply_markup=kb.as_markup()
        )
    except (KeyError, ValueError, TypeError, OverflowError, sqlite3.Error):
        logger.exception("Error in process_conversion for user %s", user_id)
        await message.answer(LANGUAGES[user_lang]['error'])
    except TelegramAPIError as e:
        logger.warning("Failed to send conversion for user %s: %s", user_id, e)


@router.message()
async def handle_message(message: types.Message):
    from_user = message.from_user
    if from_user is None:
        logger.debug("Received message without user in chat %s", message.chat.id)
        return

    logger.debug("Received message: %s from user %s in chat %s", message.text, from_user.id, message.chat.id)

    if message.text is None:
        logger.debug("Received message without text from user %s in chat %s", from_user.id, message.chat.id)
        return

    if from_user.is_bot:
        return

    if len(message.text) > 500:
        logger.debug("Message too long from user %s, ignoring", from_user.id)
        return

    if URL_OR_QUERY_TEXT_REGEX.search(message.text):
        logger.debug("Ignoring query-like text from user %s: %s", from_user.id, message.text)
        return

    user_id = from_user.id

    if message.text.startswith('/'):
        return

    parts = _SEPARATORS_REGEX.split(message.text)

    requests = []
    for i, part in enumerate(parts):
        if i % 2 == 0 and part.strip():
            requests.append(part.strip())

    if len(requests) == 0:
        requests = [message.text]

    valid_requests = []

    for request in requests:
        parsed_result = parse_amount_and_currency(request)
        if parsed_result[0] is not None and parsed_result[1] is not None:
            valid_requests.append((parsed_result, request))

    if valid_requests:
        await user_data.update_user_data(user_id, language_code=from_user.language_code)

        if len(valid_requests) > 10:
            valid_requests = valid_requests[:10]
            logger.warning(f"User {user_id} sent too many conversion requests, truncated to 10")

        if len(valid_requests) > 1:
            await process_multiple_conversions(message, [(a, c) for (a, c), _ in valid_requests])
        else:
            (amount, currency), original_text = valid_requests[0]
            target = find_target_currency(original_text, currency)
            if target and target in ALL_CURRENCIES:
                await process_targeted_conversion(message, amount, currency, target)
            else:
                await process_conversion(message, amount, currency)
    else:
        has_numbers = any(char.isdigit() for char in message.text)
        if not has_numbers:
            return

        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            user_lang = (await user_data.get_chat_data(message.chat.id)).get('language', 'ru')
        else:
            user_lang = (await user_data.get_user_data(user_id)).get('language', 'ru')

        text_cleaned = message.text.strip()
        if is_math_expression(text_cleaned):
            expr_normalized = text_cleaned.replace(' ', '').replace(',', '.')
            math_result = parse_mathematical_expression(expr_normalized)
            if math_result is not None:
                kb = _build_delete_conversion_kb(user_lang)
                response = build_math_response(user_lang, text_cleaned, math_result)
                await message.reply(text=response, reply_markup=kb.as_markup())
                return

        if message.chat.type == ChatType.PRIVATE:
            unknown_cur = extract_unknown_currency(message.text)
            if unknown_cur and unknown_cur.lower() not in PATTERN_TO_CODE:
                suggestions = find_similar_currencies(unknown_cur)
                if suggestions:
                    formatted = ", ".join(f"<b>{s}</b>" for s in suggestions)
                    error_msg = LANGUAGES[user_lang].get(
                        'unknown_currency',
                        '⚠️ Currency <b>{currency}</b> not found.\n\nDid you mean: {suggestions}?\n\nCurrency list — /settings'
                    ).format(currency=unknown_cur.upper(), suggestions=formatted)
                else:
                    error_msg = LANGUAGES[user_lang].get(
                        'unknown_currency_no_suggestions',
                        '⚠️ Currency <b>{currency}</b> not found.\n\nUse codes like: USD, EUR, RUB, etc.\nCurrency list — /settings'
                    ).format(currency=unknown_cur.upper())

                await message.reply(text=error_msg)
                return

        if contains_known_currency(message.text):
            bounds_state = detect_amount_bounds_from_text(message.text)
            if bounds_state == 'too_large':
                await reply_ephemeral_or_fallback(message, format_too_large_message(user_lang))
                return
            if bounds_state == 'too_small':
                await reply_ephemeral_or_fallback(message, format_too_small_message(user_lang))
                return
            await reply_ephemeral_or_fallback(
                message,
                LANGUAGES[user_lang].get(
                    'invalid_amount_or_too_large',
                    'Could not parse amount. Check number format (e.g., 100.50 USD).'
                )
            )
            return

        trigger_words = {
            'ru': ['конвертировать', 'перевести', 'convert'],
            'en': ['convert', 'exchange', 'convert']
        }

        has_trigger_word = any(word in message.text.lower() for word in trigger_words.get(user_lang, trigger_words['en']))

        if has_trigger_word:
            kb = InlineKeyboardBuilder()
            kb.row(primary_button(LANGUAGES[user_lang].get('help_button', 'Help'), "howto", emoji=EMOJI['help']))

            error_message = LANGUAGES[user_lang].get(
                'conversion_help_message',
                LANGUAGES['en']['conversion_help_message']
            )

            await message.reply(
                error_message,
                reply_markup=kb.as_markup()
            )

        logger.debug("No valid conversion requests found in message: %s from user %s", message.text, user_id)


@router.my_chat_member()
async def handle_my_chat_member(event: ChatMemberUpdated, bot: Bot):
    logger.info(f"Bot status changed in chat {event.chat.id}")
    logger.debug("Event content: %s", event.model_dump_json())

    if event.new_chat_member.status == ChatMemberStatus.MEMBER:
        try:
            await user_data.initialize_chat_settings(event.chat.id)
            chat_lang = await user_data.get_chat_language(event.chat.id)
            welcome_message = LANGUAGES[chat_lang]['welcome_group_message']
            await bot.send_message(event.chat.id, welcome_message)
            logger.info(f"Welcome message sent to chat {event.chat.id}")
        except (TelegramAPIError, sqlite3.Error) as e:
            logger.warning(f"Failed to handle chat member update for chat {event.chat.id}: {e}")
