import logging
import sqlite3

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputRichMessageContent,
    InputTextMessageContent,
)

from config.config import (
    ALL_CURRENCIES,
    CRYPTO_CURRENCIES,
    MAX_CONVERSION_AMOUNT,
    MIN_CONVERSION_AMOUNT,
)
from config.languages import LANGUAGES
from loader import user_data
from utils.formatter import (
    FORMAT_QUOTE,
    FORMAT_TABLE,
    build_conversion_rich_message,
    build_math_response,
    build_rich_rows,
    format_large_number,
    format_too_large_message,
    format_too_small_message,
    get_currency_symbol,
    resolve_display_format,
)
from utils.parser import (
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

logger = logging.getLogger(__name__)
router = Router()


def _article(
    article_id: str,
    title: str,
    description: str,
    message_text: str,
    *,
    parse_mode: ParseMode | None = None,
) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=article_id,
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode=parse_mode,
        ),
    )


def _settings_button(user_lang: str) -> InlineQueryResultsButton:
    return InlineQueryResultsButton(
        text=LANGUAGES[user_lang].get('inline_open_settings', '⚙️ Configure currencies'),
        start_parameter='settings',
    )


def _build_inline_section(
    amount: float,
    from_currency: str,
    targets: list[str],
    rates: dict,
    title: str,
    *,
    is_crypto: bool,
    use_quote: bool,
) -> str:
    body_lines = []
    for to_cur in targets:
        if to_cur == from_currency:
            continue
        try:
            converted = convert_currency(amount, from_currency, to_cur, rates)
            body_lines.append(f"{format_large_number(converted, is_crypto)} {get_currency_symbol(to_cur)}{to_cur}")
        except (KeyError, ValueError, OverflowError):
            continue

    body = "\n".join(body_lines)
    if body:
        body += "\n"
    if use_quote:
        body = f"<blockquote expandable>{body}</blockquote>"
    return f"<b>{title}</b>\n\n{body}"


@router.inline_query()
async def inline_query_handler(query: InlineQuery):
    if len(query.query) > 100:
        return

    if URL_OR_QUERY_TEXT_REGEX.search(query.query):
        return

    user_lang = 'en'

    try:
        if not query.query.strip():
            await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
            data = await user_data.get_user_data(query.from_user.id)
            user_lang = data.get('language', 'ru')
            empty_result = _article(
                "empty_input",
                LANGUAGES[user_lang].get('empty_input_title', "Enter amount and currency"),
                LANGUAGES[user_lang].get('empty_input_description', "For example, '100 USD' or '10,982 KZT'"),
                LANGUAGES[user_lang].get(
                    'empty_input_message',
                    "Please enter an amount and currency code to convert, e.g., '100 USD' or '10,982 KZT'.",
                ),
            )
            await query.answer(
                results=[empty_result],
                cache_time=60,
                is_personal=True,
                button=_settings_button(user_lang),
            )
            return

        amount, from_currency = parse_amount_and_currency(query.query)

        if amount is None or from_currency is None:
            await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
            data = await user_data.get_user_data(query.from_user.id)
            user_lang = data.get('language', 'ru')

            text = query.query.strip()

            if is_math_expression(text):
                expr_normalized = text.replace(' ', '').replace(',', '.')
                math_result = parse_mathematical_expression(expr_normalized)
                if math_result is not None:
                    result_str = format_large_number(math_result)
                    response = build_math_response(user_lang, text, math_result)
                    math_article = _article(
                        "math_result",
                        f"{text} = {result_str}",
                        LANGUAGES[user_lang].get('conversion_result', "Result"),
                        response,
                        parse_mode=ParseMode.HTML,
                    )
                    await query.answer(results=[math_article], cache_time=60, is_personal=True)
                    return

            unknown_cur = extract_unknown_currency(text)
            if unknown_cur:
                suggestions = find_similar_currencies(unknown_cur)
                if suggestions:
                    results = [
                        _article(
                            f"suggest_{code}",
                            f"{get_currency_symbol(code)}{code}",
                            LANGUAGES[user_lang].get('invalid_input_description', "Tap to use this currency"),
                            LANGUAGES[user_lang].get(
                                'empty_input_message',
                                "Enter amount and currency code to convert.",
                            ),
                        )
                        for code in suggestions
                    ]
                    await query.answer(results=results, cache_time=60, is_personal=True)
                    return

            if contains_known_currency(text):
                bounds_state = detect_amount_bounds_from_text(text)
                if bounds_state == 'too_large':
                    msg = format_too_large_message(user_lang)
                    await query.answer(
                        results=[
                            _article(
                                "too_large_invalid",
                                msg,
                                LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                                msg,
                            )
                        ],
                        cache_time=30,
                        is_personal=True,
                    )
                    return
                if bounds_state == 'too_small':
                    msg = format_too_small_message(user_lang)
                    await query.answer(
                        results=[
                            _article(
                                "too_small_invalid",
                                msg,
                                LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                                msg,
                            )
                        ],
                        cache_time=30,
                        is_personal=True,
                    )
                    return

            error_result = _article(
                "error",
                LANGUAGES[user_lang].get('empty_input_title', "Enter amount and currency"),
                LANGUAGES[user_lang].get('empty_input_description', "For example, '100 USD' or '10,982 KZT'"),
                LANGUAGES[user_lang].get(
                    'empty_input_message',
                    "Enter amount and currency code: 100 USD or 10,982 KZT.",
                ),
            )
            await query.answer(results=[error_result], cache_time=60, is_personal=True)
            return

        await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
        data = await user_data.get_user_data(query.from_user.id)
        user_lang = data.get('language', 'ru')
        display_format = resolve_display_format(
            data.get('use_quote_format', True),
            data.get('use_rich_format', False),
        )
        use_quote = display_format == FORMAT_QUOTE
        use_rich = display_format == FORMAT_TABLE
        user_currencies = data.get('selected_currencies', [])
        user_crypto = data.get('selected_crypto', [])

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        if amount > MAX_CONVERSION_AMOUNT:
            msg = format_too_large_message(user_lang)
            await query.answer(
                results=[
                    _article(
                        "too_large",
                        msg,
                        LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                        msg,
                    )
                ],
                cache_time=30,
                is_personal=True,
            )
            return

        if amount < MIN_CONVERSION_AMOUNT:
            msg = format_too_small_message(user_lang)
            await query.answer(
                results=[
                    _article(
                        "too_small",
                        msg,
                        LANGUAGES[user_lang].get('invalid_input_description', 'Check your input format'),
                        msg,
                    )
                ],
                cache_time=30,
                is_personal=True,
            )
            return

        rates = await get_exchange_rates()
        if not rates:
            return

        inline_target = find_target_currency(query.query, from_currency)
        if inline_target is not None and inline_target in ALL_CURRENCIES and inline_target != from_currency:
            converted = convert_currency(amount, from_currency, inline_target, rates)
            is_crypto = inline_target in CRYPTO_CURRENCIES
            targeted_content = (
                f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n"
                f"= {format_large_number(converted, is_crypto)} {get_currency_symbol(inline_target)}{inline_target}"
            )
            targeted_result = _article(
                f"{from_currency}_{inline_target}",
                f"{from_currency} -> {inline_target}",
                LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
                targeted_content,
                parse_mode=ParseMode.HTML,
            )
            await query.answer(results=[targeted_result], cache_time=60, is_personal=True)
            return

        if not user_currencies and not user_crypto:
            no_currency_result = _article(
                "no_currencies",
                LANGUAGES[user_lang].get('no_currencies_selected', "No currencies selected"),
                LANGUAGES[user_lang].get('select_currencies_message', "Please select currencies in settings"),
                LANGUAGES[user_lang].get(
                    'select_currencies_full_message',
                    "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.",
                ),
            )
            await query.answer(
                results=[no_currency_result],
                cache_time=60,
                is_personal=True,
                button=_settings_button(user_lang),
            )
            return

        sections = []
        if user_currencies:
            sections.append(
                _build_inline_section(
                    amount,
                    from_currency,
                    user_currencies,
                    rates,
                    LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies'),
                    is_crypto=False,
                    use_quote=use_quote,
                )
            )
        if user_crypto:
            sections.append(
                _build_inline_section(
                    amount,
                    from_currency,
                    user_crypto,
                    rates,
                    LANGUAGES[user_lang].get('cryptocurrencies_output', 'Cryptocurrencies'),
                    is_crypto=True,
                    use_quote=use_quote,
                )
            )

        header = f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}\n\n"
        result_content = header + "\n".join(sections)

        title = LANGUAGES[user_lang].get('conversion_result', "Conversion Result")
        description = f"{amount} {from_currency} to your selected currencies"
        fallback_result = _article(
            f"{from_currency}_all",
            title,
            description,
            result_content,
            parse_mode=ParseMode.HTML,
        )

        if use_rich:
            fiat_rows = build_rich_rows(amount, from_currency, user_currencies, rates, False) if user_currencies else []
            crypto_rows = build_rich_rows(amount, from_currency, user_crypto, rates, True) if user_crypto else []
            if fiat_rows or crypto_rows:
                rich_msg = build_conversion_rich_message(
                    amount, from_currency, fiat_rows, crypto_rows, user_lang, use_quote=False
                )
                rich_result = InlineQueryResultArticle(
                    id=f"{from_currency}_all",
                    title=title,
                    description=description,
                    input_message_content=InputRichMessageContent(rich_message=rich_msg),
                )
                try:
                    logger.info(
                        "Successful inline rich conversion for user %s: %s %s",
                        query.from_user.id,
                        amount,
                        from_currency,
                    )
                    await query.answer(results=[rich_result], cache_time=60, is_personal=True)
                    return
                except TelegramBadRequest as e:
                    logger.debug(
                        "Inline InputRichMessageContent rejected for user %s, falling back to HTML: %s",
                        query.from_user.id,
                        e,
                    )

        logger.info(f"Successful inline conversion for user {query.from_user.id}: {amount} {from_currency}")
        await query.answer(results=[fallback_result], cache_time=60, is_personal=True)
    except ValueError as ve:
        error_result = _article(
            "error",
            LANGUAGES[user_lang].get('invalid_input', "Invalid Input"),
            str(ve),
            LANGUAGES[user_lang].get(
                'invalid_input_message',
                "Invalid input. Please enter amount and currency code, e.g., '100 USD'.",
            ),
        )
        await query.answer(results=[error_result], cache_time=60, is_personal=True)
    except (KeyError, TypeError, OverflowError, sqlite3.Error):
        logger.exception("Error during inline conversion for user %s", query.from_user.id)
        error_result = _article(
            "error",
            LANGUAGES[user_lang].get('error', "Error"),
            LANGUAGES[user_lang].get('error_occurred', "An error occurred. Please try again."),
            LANGUAGES[user_lang].get('error_message', "An error occurred. Please try again."),
        )
        await query.answer(results=[error_result], cache_time=60, is_personal=True)
    except TelegramAPIError as e:
        logger.warning("Failed to answer inline query for user %s: %s", query.from_user.id, e)
