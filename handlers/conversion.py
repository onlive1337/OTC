import re
import logging
from typing import List, Tuple, Optional

from aiogram import Router, types, Bot
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import ALL_CURRENCIES, CURRENCY_SYMBOLS, CURRENCY_ABBREVIATIONS, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from loader import user_data
from utils.utils import get_exchange_rates, convert_currency, format_large_number, parse_amount_and_currency
from utils.button_styles import danger_button, primary_button, EMOJI

logger = logging.getLogger(__name__)
router = Router()


_TARGET_CURRENCY_PATTERNS = {}
_TARGET_CURRENCY_PATTERNS.update(CURRENCY_SYMBOLS)
_TARGET_CURRENCY_PATTERNS.update(CURRENCY_ABBREVIATIONS)
_TARGET_CURRENCY_PATTERNS.update({k.upper(): k.upper() for k in ALL_CURRENCIES.keys()})

_TARGET_PATTERNS_LOWER = {p.lower(): c for p, c in _TARGET_CURRENCY_PATTERNS.items()}

_SPLIT_TOKENS_REGEX = re.compile(r'[\s,]+')
_SKIP_TOKENS_REGEX = re.compile(r'^[\d.,+\-*/()^×÷:хk]+$')

_SEPARATORS = [
    r'\s+и\s+', r'\s+and\s+', r'\s+а\s+также\s+', 
    r';', r'\n', r',\s+(?=\d)', r'\s+\+\s+'
]
_SEPARATORS_REGEX = re.compile(f"({'|'.join(_SEPARATORS)})", re.IGNORECASE)


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


async def process_targeted_conversion(message: types.Message, amount: float, from_currency: str, to_currency: str):
    user_id = message.from_user.id
    if message.chat.type in ('group', 'supergroup'):
        data = await user_data.get_chat_data(message.chat.id)
        user_lang = data.get('language', 'ru')
    else:
        data = await user_data.get_user_data(user_id)
        user_lang = data.get('language', 'ru')

    try:
        if amount <= 0:
            await message.answer(LANGUAGES[user_lang].get('negative_or_zero_amount'))
            return

        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return

        converted = convert_currency(amount, from_currency, to_currency, rates)
        is_crypto = to_currency in CRYPTO_CURRENCIES

        response = (
            f"{format_large_number(amount, is_original_amount=True)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n"
            f"= {format_large_number(converted, is_crypto)} {ALL_CURRENCIES.get(to_currency, '')} {to_currency}"
        )

        kb = InlineKeyboardBuilder()
        kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', 'Delete'), 'delete_conversion', emoji=EMOJI['delete']))

        await message.reply(text=response, reply_markup=kb.as_markup(), parse_mode="HTML")
    except KeyError:
        await message.answer(LANGUAGES[user_lang]['error'])
    except Exception as e:
        logger.error(f"Error in targeted conversion for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def process_multiple_conversions(message: types.Message, requests: List[Tuple[float, str]]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    await user_data.update_user_data(user_id)
    
    if message.chat.type in ('group', 'supergroup'):
        data = await user_data.get_chat_data(chat_id)
        user_lang = data.get('language', 'ru')
        user_currencies = data.get('currencies', [])
        user_crypto = data.get('crypto', [])
        use_quote = data.get('quote_format', False)
    else:
        data = await user_data.get_user_data(user_id)
        user_lang = data.get('language', 'ru')
        user_currencies = data.get('selected_currencies', [])
        user_crypto = data.get('selected_crypto', [])
        use_quote = data.get('use_quote_format', True)
    
    try:
        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return
        
        final_response = ""
        
        for amount, from_currency in requests:
            if amount <= 0 or amount > 1e100 or amount < -1e100:
                continue
            
            response = f"{format_large_number(amount, is_original_amount=True)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n"
            conversion_parts = []
            
            if user_currencies:
                conversion_parts.append(f"{LANGUAGES[user_lang]['fiat_currencies']}")
                fiat_parts = []
                for to_cur in user_currencies:
                    if to_cur != from_currency:
                        try:
                            converted = convert_currency(amount, from_currency, to_cur, rates)
                            fiat_parts.append(f"{format_large_number(converted)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}")
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
            kb = InlineKeyboardBuilder()
            kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', "Delete"), "delete_conversion", emoji=EMOJI['delete']))
            
            await message.reply(
                text=final_response.strip(),
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error in process_multiple_conversions for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def process_conversion(message: types.Message, amount: float, from_currency: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.chat.type in ('group', 'supergroup'):
        data = await user_data.get_chat_data(chat_id)
        user_lang = data.get('language', 'ru')
        user_currencies = data.get('currencies', [])
        user_crypto = data.get('crypto', [])
        use_quote = data.get('quote_format', False)
    else:
        data = await user_data.get_user_data(user_id)
        user_lang = data.get('language', 'ru')
        user_currencies = data.get('selected_currencies', [])
        user_crypto = data.get('selected_crypto', [])
        use_quote = data.get('use_quote_format', True)
    
    try:
        if amount <= 0:
            await message.answer(LANGUAGES[user_lang].get('negative_or_zero_amount'))
            return

        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return
        
        response_parts = []
        response_parts.append(f"{format_large_number(amount, is_original_amount=True)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n")

        if user_currencies:
            response_parts.append(f"\n{LANGUAGES[user_lang]['fiat_currencies']}\n")
            fiat_conversions = []
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
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
        
        kb = InlineKeyboardBuilder()
        kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', "Delete"), "delete_conversion", emoji=EMOJI['delete']))
        
        final_response = "".join(response_parts).strip()
        
        await message.reply(
            text=final_response,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in process_conversion for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

@router.message()
async def handle_message(message: types.Message):
    logger.debug("Received message: %s from user %s in chat %s", message.text, message.from_user.id, message.chat.id)
    
    if message.text is None:
        logger.debug("Received message without text from user %s in chat %s", message.from_user.id, message.chat.id)
        return

    if len(message.text) > 500:
        logger.debug("Message too long from user %s, ignoring", message.from_user.id)
        return

    user_id = message.from_user.id
    await user_data.update_user_data(user_id, language_code=message.from_user.language_code)

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
        trigger_words = {
            'ru': ['конвертировать', 'перевести', 'convert'],
            'en': ['convert', 'exchange', 'convert']
        }
        
        has_numbers = any(char.isdigit() for char in message.text)
        if has_numbers:
            if message.chat.type in ('group', 'supergroup'):
                user_lang = (await user_data.get_chat_data(message.chat.id)).get('language', 'ru')
            else:
                user_lang = (await user_data.get_user_data(user_id)).get('language', 'ru')

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
    await user_data.update_user_data(query.from_user.id, language_code=query.from_user.language_code)
    data = await user_data.get_user_data(query.from_user.id)
    user_lang = data.get('language', 'ru')
    use_quote = data.get('use_quote_format', True)

    if len(query.query) > 100:
        return

    if not query.query.strip():
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
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('invalid_input', "Invalid Input"),
            description=LANGUAGES[user_lang].get('invalid_input_description', "Please check your input format"),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('invalid_input_message', 
                "Invalid input. Please enter amount and currency code, e.g., '100 USD' or '10,982 KZT'.")
            )
        )
        await query.answer(results=[error_result], cache_time=60)
        return

    try:
        user_currencies = data.get('selected_currencies', [])
        user_crypto = data.get('selected_crypto', [])

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        rates = await get_exchange_rates()
        if not rates:
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

        result_content = f"{format_large_number(amount, is_original_amount=True)} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        
        if user_currencies:
            result_content += f"<b>{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}</b>\n\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        result_content += f"{format_large_number(converted)} {ALL_CURRENCIES[to_cur]} {to_cur}\n"
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
                        result_content += f"{format_large_number(converted, True)} {ALL_CURRENCIES[to_cur]}\n"
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
        await user_data.initialize_chat_settings(event.chat.id)
        
        user_lang = await user_data.get_user_language(event.from_user.id)
        
        welcome_message = LANGUAGES[user_lang]['welcome_group_message']
        
        await bot.send_message(event.chat.id, welcome_message)
        logger.info(f"Welcome message sent to chat {event.chat.id}")