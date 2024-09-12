import logging
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineQuery
from config import ALL_CURRENCIES, CURRENCY_SYMBOLS
from user_data import UserData
from languages import LANGUAGES

logger = logging.getLogger(__name__)    
user_data = UserData()

def import_main():
    global get_exchange_rates, convert_currency, format_large_number
    from main import get_exchange_rates, convert_currency, format_large_number

async def inline_query_handler(query: InlineQuery):
    user_id = query.from_user.id
    user_data.update_user_data(user_id)
    user_lang = user_data.get_user_language(user_id)
    use_quote = user_data.get_user_quote_format(user_id)
    args = query.query.split()
    import_main()

    if len(args) < 2:
        return

    try:
        amount = float(args[0])
        from_currency = CURRENCY_SYMBOLS.get(args[1].upper(), args[1].upper())

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        rates = await get_exchange_rates()
        if not rates:
            logger.error("Failed to get exchange rates")
            return

        user_currencies = user_data.get_user_currencies(user_id)
        user_crypto = user_data.get_user_crypto(user_id)

        result_content = f"{format_large_number(amount)} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"

        if user_currencies:
            result_content += f"<b>{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}</b>\n"
            result_content += "\n".join(
                f"{format_large_number(convert_currency(amount, from_currency, to_cur, rates))} {ALL_CURRENCIES[to_cur]} {to_cur}"
                for to_cur in user_currencies if to_cur != from_currency
            )
            result_content += "\n\n"

        if user_crypto:
            result_content += f"<b>{LANGUAGES[user_lang].get('cryptocurrencies_output', 'Cryptocurrencies')}</b>\n"
            result_content += "\n".join(
                f"{format_large_number(convert_currency(amount, from_currency, to_cur, rates), True)} {ALL_CURRENCIES[to_cur]} {to_cur}"
                for to_cur in user_crypto if to_cur != from_currency
            )

        if use_quote:
            result_content = f"<blockquote expandable>{result_content}</blockquote>"

        result = InlineQueryResultArticle(
            id=f"{from_currency}_all",
            title=LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
            description=f"{amount} {from_currency} to your selected currencies",
            input_message_content=InputTextMessageContent(
                message_text=result_content,
                parse_mode="HTML"
            )
        )

        logger.info(f"Successful inline conversion for user {user_id}: {amount} {from_currency}")
        await query.answer(results=[result], cache_time=1)
    except Exception as e:
        logger.error(f"Error during inline conversion for user {user_id}: {str(e)}")
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('error', "Error"),
            description=LANGUAGES[user_lang].get('error_occurred', "An error occurred. Please try again."),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('error_message', "An error occurred. Please try again.")
            )
        )
        await query.answer(results=[error_result], cache_time=1)