import difflib
import re
import logging
from decimal import Decimal, InvalidOperation
from typing import List, Tuple, Optional

from aiogram import Router, types, Bot
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import (
    ALL_CURRENCIES,
    CURRENCY_SYMBOLS,
    CURRENCY_ABBREVIATIONS,
    CRYPTO_CURRENCIES,
    MAX_CONVERSION_AMOUNT,
    MIN_CONVERSION_AMOUNT,
)
from config.languages import LANGUAGES
from loader import user_data
from utils.rates import get_exchange_rates, convert_currency
from utils.formatter import format_large_number, get_currency_symbol
from utils.parser import parse_amount_and_currency, parse_mathematical_expression
from utils.button_styles import danger_button, primary_button, EMOJI

logger = logging.getLogger(__name__)
router = Router()


_TARGET_CURRENCY_PATTERNS = {}
_TARGET_CURRENCY_PATTERNS.update(CURRENCY_SYMBOLS)
_TARGET_CURRENCY_PATTERNS.update(CURRENCY_ABBREVIATIONS)
_TARGET_CURRENCY_PATTERNS.update({k.upper(): k.upper() for k in ALL_CURRENCIES.keys()})

_TARGET_PATTERNS_LOWER = {p.lower(): c for p, c in _TARGET_CURRENCY_PATTERNS.items()}

_KNOWN_CURRENCY_REGEX_PARTS = []
for pattern in sorted(_TARGET_PATTERNS_LOWER.keys(), key=len, reverse=True):
    pattern_str = str(pattern)
    starts_with_word = re.match(r'^\w', pattern_str, re.UNICODE) is not None
    ends_with_word = re.search(r'\w$', pattern_str, re.UNICODE) is not None
    prefix = r'(?<!\w)' if starts_with_word else ''
    suffix = r'(?!\w)' if ends_with_word else ''
    _KNOWN_CURRENCY_REGEX_PARTS.append(rf'{prefix}{re.escape(pattern_str)}{suffix}')
_KNOWN_CURRENCY_REGEX = re.compile('|'.join(_KNOWN_CURRENCY_REGEX_PARTS), re.IGNORECASE)

_SPLIT_TOKENS_REGEX = re.compile(r'[\s,]+')
_SKIP_TOKENS_REGEX = re.compile(r'^[\d.,+\-*/()^×÷:хk]+$')
_QUERY_LIKE_TEXT_REGEX = re.compile(
    r'https?://\S+|\b\S+\.(?:php|aspx?|jsp|html?)\?\S*\b|\b[a-zA-Z]{2,10}\?\d+\b',
    re.IGNORECASE,
)

_SEPARATORS = [
    r'\s+и\s+', r'\s+and\s+', r'\s+а\s+также\s+', 
    r';', r'\n', r',\s+(?=\d)', r'\s+\+\s+'
]
_SEPARATORS_REGEX = re.compile(f"({'|'.join(_SEPARATORS)})", re.IGNORECASE)

_MATH_ONLY_REGEX = re.compile(
    r'^[\d\s.,+\-*/()^×÷:хk]+$'
)

_MAX_SAFE_CONVERSION_AMOUNT = MAX_CONVERSION_AMOUNT
_MIN_SAFE_CONVERSION_AMOUNT = MIN_CONVERSION_AMOUNT

_ALL_KNOWN_CODES = set(k.upper() for k in ALL_CURRENCIES.keys())
_ALL_KNOWN_WORDS = set()
for p in CURRENCY_SYMBOLS:
    _ALL_KNOWN_WORDS.add(p.lower())
for p in CURRENCY_ABBREVIATIONS:
    _ALL_KNOWN_WORDS.add(p.lower())
for k in ALL_CURRENCIES:
    _ALL_KNOWN_WORDS.add(k.lower())


def _find_similar_currencies(text: str, max_results: int = 3) -> List[str]:
    text_upper = text.upper().strip()
    text_lower = text.lower().strip()
    
    suggestions = []
    
    code_matches = difflib.get_close_matches(text_upper, _ALL_KNOWN_CODES, n=max_results, cutoff=0.5)
    suggestions.extend(code_matches)
    
    if len(suggestions) < max_results:
        word_matches = difflib.get_close_matches(text_lower, _ALL_KNOWN_WORDS, n=max_results, cutoff=0.5)
        for w in word_matches:
            code = _TARGET_PATTERNS_LOWER.get(w)
            if code and code not in suggestions:
                suggestions.append(code)
    
    return suggestions[:max_results]


def _extract_unknown_currency(text: str) -> Optional[str]:
    text = text.strip()

    unknown_currency_pattern = re.compile(
        r'^([\d\s.,]+)\s+([a-zA-Zа-яА-ЯёЁ]{2,10})$'
        r'|^([a-zA-Zа-яА-ЯёЁ]{2,10})\s+([\d\s.,]+)$'
    )
    m = unknown_currency_pattern.match(text)
    if m:
        if m.group(2):
            return m.group(2)
        elif m.group(3):
            return m.group(3)
    return None



def _find_target_currency(text: str, from_currency: str) -> Optional[str]:
    tokens = _SPLIT_TOKENS_REGEX.split(text.strip())
    found = []
    for token in tokens:
        token_lower = token.lower().strip()
        if not token_lower or _SKIP_TOKENS_REGEX.match(token_lower):
            continue
        code = _TARGET_PATTERNS_LOWER.get(token_lower)
        if code and code != from_currency and code not in found:
            found.append(code)

    return found[0] if len(found) == 1 else None


def _contains_known_currency(text: str) -> bool:
    if _QUERY_LIKE_TEXT_REGEX.search(text):
        return False
    return _KNOWN_CURRENCY_REGEX.search(text.lower()) is not None


def _too_large_message(user_lang: str) -> str:
    default_msg = f"Number is too large. Max allowed: {format_large_number(_MAX_SAFE_CONVERSION_AMOUNT, is_original_amount=True)}"
    template = LANGUAGES[user_lang].get('number_too_large', default_msg)
    if '{max_amount}' in template:
        return template.format(max_amount=format_large_number(_MAX_SAFE_CONVERSION_AMOUNT, is_original_amount=True))
    return template


def _too_small_message(user_lang: str) -> str:
    default_msg = f"Amount is too small. Minimum: {format_large_number(_MIN_SAFE_CONVERSION_AMOUNT, is_original_amount=True)}"
    template = LANGUAGES[user_lang].get('number_too_small', default_msg)
    if '{min_amount}' in template:
        return template.format(min_amount=format_large_number(_MIN_SAFE_CONVERSION_AMOUNT, is_original_amount=True))
    return template


def _detect_amount_bounds_from_text(text: str) -> Optional[str]:
    amount_text = _KNOWN_CURRENCY_REGEX.sub('', text.lower()).replace(' ', '')
    candidates = re.findall(r'[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][-+]?\d+)?', amount_text)

    max_amount = Decimal(str(_MAX_SAFE_CONVERSION_AMOUNT))
    min_amount = Decimal(str(_MIN_SAFE_CONVERSION_AMOUNT))

    for token in candidates:
        normalized = token.replace(',', '.')
        try:
            value = Decimal(normalized)
        except (InvalidOperation, ValueError):
            continue

        if not value.is_finite() or value.is_nan():
            continue
        if value <= 0:
            continue
        if value > max_amount:
            return 'too_large'
        if value < min_amount:
            return 'too_small'

    return None


async def _validate_amount_or_reply(message: types.Message, user_lang: str, amount: float) -> bool:
    if amount <= 0:
        await message.answer(LANGUAGES[user_lang].get('negative_or_zero_amount'))
        return False
    if amount < _MIN_SAFE_CONVERSION_AMOUNT:
        await message.answer(_too_small_message(user_lang))
        return False
    if amount > _MAX_SAFE_CONVERSION_AMOUNT:
        await message.answer(_too_large_message(user_lang))
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
            False if message.chat.type in ('group', 'supergroup') else True,
            0,
            message.chat.id,
        )

    user_id = from_user.id
    if message.chat.type in ('group', 'supergroup'):
        data = await user_data.get_chat_data(message.chat.id)
        return (
            data.get('language', 'ru'),
            data.get('currencies', []),
            data.get('crypto', []),
            data.get('quote_format', False),
            user_id,
            message.chat.id,
        )

    data = await user_data.get_user_data(user_id)
    return (
        data.get('language', 'ru'),
        data.get('selected_currencies', []),
        data.get('selected_crypto', []),
        data.get('use_quote_format', True),
        user_id,
        message.chat.id,
    )


def _build_delete_conversion_kb(user_lang: str):
    kb = InlineKeyboardBuilder()
    kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', 'Delete'), 'delete_conversion', emoji=EMOJI['delete']))
    return kb


def _build_math_response(user_lang: str, expression: str, result: float) -> str:
    result_str = format_large_number(result)
    total_len = len(expression) + len(result_str)
    if total_len <= 35:
        template_key = 'math_result_short'
        fallback = '{expression} = <b>{result}</b>'
    else:
        template_key = 'math_result_long'
        fallback = '{expression}\n= <b>{result}</b>'
    return LANGUAGES[user_lang].get(template_key, fallback).format(expression=expression, result=result_str)


async def process_targeted_conversion(message: types.Message, amount: float, from_currency: str, to_currency: str):
    user_lang, _, _, _, user_id, _ = await _resolve_chat_user_prefs(message)

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
    except Exception as e:
        logger.error(f"Error in targeted conversion for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def process_multiple_conversions(message: types.Message, requests: List[Tuple[float, str]]):
    user_lang, user_currencies, user_crypto, use_quote, user_id, _ = await _resolve_chat_user_prefs(message)

    try:
        rates = await _get_rates_or_reply(message, user_lang)
        if rates is None:
            return
        
        final_response = ""
        skipped_too_large = False

        for amount, from_currency in requests:
            if amount <= 0 or amount > _MAX_SAFE_CONVERSION_AMOUNT:
                if amount > _MAX_SAFE_CONVERSION_AMOUNT:
                    skipped_too_large = True
                continue
            
            response = f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
            conversion_parts = []
            
            if user_currencies:
                conversion_parts.append(f"{LANGUAGES[user_lang]['fiat_currencies']}")
                fiat_parts = []
                for to_cur in user_currencies:
                    if to_cur != from_currency:
                        try:
                            converted = convert_currency(amount, from_currency, to_cur, rates)
                            fiat_parts.append(f"{format_large_number(converted)} {get_currency_symbol(to_cur)}{to_cur}")
                        except (KeyError, OverflowError):
                            continue
                if fiat_parts:
                    conversion_parts.append("\n".join(fiat_parts))
            
            if user_crypto:
                conversion_parts.append(f"{LANGUAGES[user_lang]['cryptocurrencies_output']}")
                crypto_parts = []
                for to_cur in user_crypto:
                    if to_cur != from_currency:
                        try:
                            converted = convert_currency(amount, from_currency, to_cur, rates)
                            crypto_parts.append(f"{format_large_number(converted, True)} {to_cur}")
                        except (KeyError, OverflowError):
                            continue
                if crypto_parts:
                    conversion_parts.append("\n".join(crypto_parts))
            
            content = "\n\n".join(conversion_parts)
            if use_quote:
                response += "<blockquote expandable>" + content + "</blockquote>\n\n"
            else:
                response += content + "\n\n"
            final_response += response
        
        if final_response:
            kb = _build_delete_conversion_kb(user_lang)

            await message.reply(
                text=final_response.strip(),
                reply_markup=kb.as_markup()
            )
        elif skipped_too_large:
            await message.answer(_too_large_message(user_lang))

    except Exception as e:
        logger.error(f"Error in process_multiple_conversions for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def process_conversion(message: types.Message, amount: float, from_currency: str):
    user_lang, user_currencies, user_crypto, use_quote, user_id, _ = await _resolve_chat_user_prefs(message)

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
            fiat_conversions = []
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted)} {get_currency_symbol(to_cur)}{to_cur}"
                        fiat_conversions.append(conversion_line)
                    except KeyError:
                        continue
            if use_quote:
                response_parts.append("<blockquote expandable>" + "\n".join(fiat_conversions) + "</blockquote>")
            else:
                response_parts.append("\n".join(fiat_conversions))
        
        if user_crypto:
            response_parts.append(f"\n\n{LANGUAGES[user_lang]['cryptocurrencies_output']}\n")
            crypto_conversions = []
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted, True)} {to_cur}"
                        crypto_conversions.append(conversion_line)
                    except KeyError:
                        continue
            if use_quote:
                response_parts.append("<blockquote expandable>" + "\n".join(crypto_conversions) + "</blockquote>")
            else:
                response_parts.append("\n".join(crypto_conversions))
        
        kb = _build_delete_conversion_kb(user_lang)

        final_response = "".join(response_parts).strip()
        
        await message.reply(
            text=final_response,
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logger.error(f"Error in process_conversion for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

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

    if _QUERY_LIKE_TEXT_REGEX.search(message.text):
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
            target = _find_target_currency(original_text, currency)
            if target and target in ALL_CURRENCIES:
                await process_targeted_conversion(message, amount, currency, target)
            else:
                await process_conversion(message, amount, currency)
    else:
        has_numbers = any(char.isdigit() for char in message.text)
        if not has_numbers:
            return
        
        if message.chat.type in ('group', 'supergroup'):
            user_lang = (await user_data.get_chat_data(message.chat.id)).get('language', 'ru')
        else:
            user_lang = (await user_data.get_user_data(user_id)).get('language', 'ru')

        text_cleaned = message.text.strip()
        math_operators = {'+', '-', '*', '/', '^', '×', '÷', ':', 'х'}
        if _MATH_ONLY_REGEX.match(text_cleaned) and any(op in text_cleaned for op in math_operators):
            expr_normalized = text_cleaned.replace(' ', '').replace(',', '.')
            math_result = parse_mathematical_expression(expr_normalized)
            if math_result is not None:
                kb = _build_delete_conversion_kb(user_lang)
                response = _build_math_response(user_lang, text_cleaned, math_result)
                await message.reply(text=response, reply_markup=kb.as_markup())
                return

        if message.chat.type == 'private':
            unknown_cur = _extract_unknown_currency(message.text)
            if unknown_cur and unknown_cur.lower() not in _TARGET_PATTERNS_LOWER:
                suggestions = _find_similar_currencies(unknown_cur)
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

        if _contains_known_currency(message.text):
            bounds_state = _detect_amount_bounds_from_text(message.text)
            if bounds_state == 'too_large':
                await message.reply(_too_large_message(user_lang))
                return
            if bounds_state == 'too_small':
                await message.reply(_too_small_message(user_lang))
                return
            await message.reply(
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
            
            error_message = LANGUAGES[user_lang].get('conversion_help_message', 
                LANGUAGES['en']['conversion_help_message'])
            
            await message.reply(
                error_message,
                reply_markup=kb.as_markup()
            )
        
        logger.debug("No valid conversion requests found in message: %s from user %s", message.text, user_id)

@router.inline_query()
async def inline_query_handler(query: InlineQuery):
    if len(query.query) > 100:
        return

    user_lang = 'en'

    if _QUERY_LIKE_TEXT_REGEX.search(query.query):
        return

    if not query.query.strip():
        await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
        data = await user_data.get_user_data(query.from_user.id)
        user_lang = data.get('language', 'ru')
        empty_input_result = InlineQueryResultArticle(
            id="empty_input",
            title=LANGUAGES[user_lang].get('empty_input_title', "Enter amount and currency"),
            description=LANGUAGES[user_lang].get('empty_input_description', "For example, '100 USD' or '10,982 KZT'"),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('empty_input_message', 
                "Please enter an amount and currency code to convert, e.g., '100 USD' or '10,982 KZT'.")
            )
        )
        await query.answer(results=[empty_input_result], cache_time=60)
        return

    amount, from_currency = parse_amount_and_currency(query.query)

    if amount is None or from_currency is None:
        await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
        data = await user_data.get_user_data(query.from_user.id)
        user_lang = data.get('language', 'ru')

        text = query.query.strip()
        
        math_operators = {'+', '-', '*', '/', '^', '×', '÷', ':', 'х'}
        if _MATH_ONLY_REGEX.match(text) and any(op in text for op in math_operators):
            expr_normalized = text.replace(' ', '').replace(',', '.')
            math_result = parse_mathematical_expression(expr_normalized)
            if math_result is not None:
                result_str = format_large_number(math_result)
                response = _build_math_response(user_lang, text, math_result)
                math_article = InlineQueryResultArticle(
                    id="math_result",
                    title=f"{text} = {result_str}",
                    description=LANGUAGES[user_lang].get('conversion_result', "Result"),
                    input_message_content=InputTextMessageContent(
                        message_text=response,
                        parse_mode="HTML"
                    )
                )
                await query.answer(results=[math_article], cache_time=60)
                return

        unknown_cur = _extract_unknown_currency(text)
        if unknown_cur:
            suggestions = _find_similar_currencies(unknown_cur)
            if suggestions:
                results = []
                for i, code in enumerate(suggestions):
                    results.append(InlineQueryResultArticle(
                        id=f"suggest_{code}",
                        title=f"{get_currency_symbol(code)}{code}",
                        description=LANGUAGES[user_lang].get('invalid_input_description', "Tap to use this currency"),
                        input_message_content=InputTextMessageContent(
                            message_text=LANGUAGES[user_lang].get('empty_input_message',
                            "Enter amount and currency code to convert.")
                        )
                    ))
                await query.answer(results=results, cache_time=60)
                return

        if _contains_known_currency(text):
            bounds_state = _detect_amount_bounds_from_text(text)
            if bounds_state == 'too_large':
                too_large_result = InlineQueryResultArticle(
                    id="too_large_invalid",
                    title=_too_large_message(user_lang),
                    description=LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                    input_message_content=InputTextMessageContent(message_text=_too_large_message(user_lang)),
                )
                await query.answer(results=[too_large_result], cache_time=30)
                return
            if bounds_state == 'too_small':
                too_small_result = InlineQueryResultArticle(
                    id="too_small_invalid",
                    title=_too_small_message(user_lang),
                    description=LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                    input_message_content=InputTextMessageContent(message_text=_too_small_message(user_lang)),
                )
                await query.answer(results=[too_small_result], cache_time=30)
                return

        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('empty_input_title', "Enter amount and currency"),
            description=LANGUAGES[user_lang].get('empty_input_description', "For example, '100 USD' or '10,982 KZT'"),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('empty_input_message', 
                "Enter amount and currency code: 100 USD or 10,982 KZT.")
            )
        )
        await query.answer(results=[error_result], cache_time=60)
        return

    try:
        await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
        data = await user_data.get_user_data(query.from_user.id)
        user_lang = data.get('language', 'ru')
        use_quote = data.get('use_quote_format', True)
        user_currencies = data.get('selected_currencies', [])
        user_crypto = data.get('selected_crypto', [])

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        if amount > _MAX_SAFE_CONVERSION_AMOUNT:
            too_large_result = InlineQueryResultArticle(
                id="too_large",
                title=_too_large_message(user_lang),
                description=LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                input_message_content=InputTextMessageContent(
                    message_text=_too_large_message(user_lang)
                )
            )
            await query.answer(results=[too_large_result], cache_time=30)
            return

        if amount < _MIN_SAFE_CONVERSION_AMOUNT:
            too_small_result = InlineQueryResultArticle(
                id="too_small",
                title=_too_small_message(user_lang),
                description=LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                input_message_content=InputTextMessageContent(
                    message_text=_too_small_message(user_lang)
                )
            )
            await query.answer(results=[too_small_result], cache_time=30)
            return

        rates = await get_exchange_rates()
        if not rates:
            return

        inline_target = _find_target_currency(query.query, from_currency)
        if inline_target is not None and inline_target in ALL_CURRENCIES and inline_target != from_currency:
            target_currency = inline_target
            assert target_currency is not None
            converted = convert_currency(amount, from_currency, target_currency, rates)
            is_crypto = target_currency in CRYPTO_CURRENCIES
            targeted_content = (
                f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
                f"= {format_large_number(converted, is_crypto)} {get_currency_symbol(target_currency)}{target_currency}"
            )
            targeted_result = InlineQueryResultArticle(
                id=f"{from_currency}_{target_currency}",
                title=f"{from_currency} -> {target_currency}",
                description=LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
                input_message_content=InputTextMessageContent(
                    message_text=targeted_content,
                    parse_mode="HTML"
                )
            )
            await query.answer(results=[targeted_result], cache_time=60)
            return

        if not user_currencies and not user_crypto:
            no_currency_result = InlineQueryResultArticle(
                id="no_currencies",
                title=LANGUAGES[user_lang].get('no_currencies_selected', "No currencies selected"),
                description=LANGUAGES[user_lang].get('select_currencies_message', "Please select currencies in settings"),
                input_message_content=InputTextMessageContent(
                    message_text=LANGUAGES[user_lang].get('select_currencies_full_message', 
                    "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.")
                )
            )
            await query.answer(results=[no_currency_result], cache_time=60)
            return

        result_content = f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n\n"
        
        if user_currencies:
            result_content += f"<b>{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}</b>\n\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        result_content += f"{format_large_number(converted)} {get_currency_symbol(to_cur)}{to_cur}\n"
                    except (KeyError, OverflowError):
                        continue
            if use_quote:
                result_content += "</blockquote>"
            result_content += "\n"

        if user_crypto:
            result_content += f"<b>{LANGUAGES[user_lang].get('cryptocurrencies_output', 'Cryptocurrencies')}</b>\n\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        result_content += f"{format_large_number(converted, True)} {get_currency_symbol(to_cur)}\n"
                    except (KeyError, OverflowError):
                        continue
            if use_quote:
                result_content += "</blockquote>"

        result = InlineQueryResultArticle(
            id=f"{from_currency}_all",
            title=LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
            description=f"{amount} {from_currency} to your selected currencies",
            input_message_content=InputTextMessageContent(
                message_text=result_content,
                parse_mode="HTML"
            )
        )

        logger.info(f"Successful inline conversion for user {query.from_user.id}: {amount} {from_currency}")
        await query.answer(results=[result], cache_time=60)
    except ValueError as ve:
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('invalid_input', "Invalid Input"),
            description=str(ve),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('invalid_input_message', 
                "Invalid input. Please enter amount and currency code, e.g., '100 USD'.")
            )
        )
        await query.answer(results=[error_result], cache_time=60)
    except Exception as e:
        logger.error(f"Error during inline conversion for user {query.from_user.id}: {str(e)}")
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('error', "Error"),
            description=LANGUAGES[user_lang].get('error_occurred', "An error occurred. Please try again."),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('error_message', 
                "An error occurred. Please try again.")
            )
        )
        await query.answer(results=[error_result], cache_time=60)

@router.my_chat_member()
async def handle_my_chat_member(event: ChatMemberUpdated, bot: Bot):
    logger.info(f"Bot status changed in chat {event.chat.id}")
    logger.info(f"Event content: {event.model_dump_json()}")
    
    if event.new_chat_member.status == "member":
        try:
            await user_data.initialize_chat_settings(event.chat.id)
            
            chat_lang = await user_data.get_chat_language(event.chat.id)
            
            welcome_message = LANGUAGES[chat_lang]['welcome_group_message']
            
            await bot.send_message(event.chat.id, welcome_message)
            logger.info(f"Welcome message sent to chat {event.chat.id}")
        except Exception as e:
            logger.warning(f"Failed to handle chat member update for chat {event.chat.id}: {e}")