import asyncio
from datetime import datetime
import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, CallbackQuery, ChatMemberUpdated, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandStart
from config.config import (
    BOT_TOKEN, ADMIN_IDS, CRYPTO_CURRENCIES, CURRENT_VERSION,
    ALL_CURRENCIES
)
from utils.utils import create_crypto_chart, get_chart_image, get_crypto_history, get_exchange_rates, convert_currency, format_large_number, parse_amount_and_currency, read_changelog, delete_conversion_message, save_settings, get_current_price
from data.chat_settings import show_chat_settings, save_chat_settings, show_chat_currencies, show_chat_crypto, toggle_chat_crypto, toggle_chat_currency, back_to_chat_settings
from data.user_settings import show_currencies, show_crypto, toggle_crypto, toggle_currency, toggle_quote_format, change_language, set_language
from config.languages import LANGUAGES
from data import user_data
from utils.log_handler import setup_telegram_logging

cache: Dict[str, Any] = {}
conversion_cache = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    selecting_crypto = State()
    selecting_settings = State()

user_data = user_data.UserData()

async def get_conversion_from_cache(amount: float, from_currency: str, to_currencies: list) -> Optional[dict]:
    cache_key = f"{amount}:{from_currency}:{':'.join(sorted(to_currencies))}"
    
    if cache_key in conversion_cache:
        cached_data, timestamp = conversion_cache[cache_key]
        if time.time() - timestamp < 60: 
            return cached_data
    
    return None

async def save_conversion_to_cache(amount: float, from_currency: str, to_currencies: list, results: dict):
    cache_key = f"{amount}:{from_currency}:{':'.join(sorted(to_currencies))}"
    conversion_cache[cache_key] = (results, time.time())
    
    if len(conversion_cache) > 1000:
        sorted_cache = sorted(conversion_cache.items(), key=lambda x: x[1][1])
        for key, _ in sorted_cache[:500]:
            del conversion_cache[key]

async def cmd_start(message: Message):
    user_data.update_user_data(message.from_user.id)
    logger.info(f"User {message.from_user.id} started the bot in chat {message.chat.id}")
    
    user_lang = user_data.get_user_language(message.from_user.id)
    
    if message.chat.type in ['group', 'supergroup']:
        chat_member = await message.chat.get_member(message.from_user.id)
        if chat_member.status in ['creator', 'administrator']:
            await show_chat_settings(message)
        else:
            await message.answer(LANGUAGES[user_lang]['admin_only'])
    else:
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['news_button'], url="https://t.me/OTC_InfoHub")
        kb.button(text=LANGUAGES[user_lang]['help_button'], callback_data='howto')
        kb.button(text=LANGUAGES[user_lang]['feedback_button'], callback_data='feedback')
        kb.button(text=LANGUAGES[user_lang]['settings_button'], callback_data='settings')
        kb.button(text=LANGUAGES[user_lang]['about_button'], callback_data='about')
        kb.button(text=LANGUAGES[user_lang]['support_button'], callback_data='support')
        kb.adjust(2, 2, 1, 1)
        
        welcome_message = LANGUAGES[user_lang]['welcome']
        
        await message.answer(welcome_message, reply_markup=kb.as_markup())

async def cmd_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_lang = user_data.get_user_language(user_id)

    if message.chat.type == 'private':
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
        kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
        kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
        kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
        kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
        kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
        kb.adjust(2, 2, 1, 1)
        
        use_quote = user_data.get_user_quote_format(user_id)
        quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
        settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
        
        await message.answer(settings_text, reply_markup=kb.as_markup())
    else:
        chat_member = await message.chat.get_member(user_id)
        if chat_member.status in ['creator', 'administrator']:
            kb = InlineKeyboardBuilder()
            kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data=f"show_chat_currencies_{chat_id}_0")
            kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data=f"show_chat_crypto_{chat_id}")
            kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data=f"toggle_chat_quote_format_{chat_id}")
            kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
            kb.adjust(2, 1, 1)
            
            use_quote = user_data.get_chat_quote_format(chat_id)
            quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
            settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
            
            await message.answer(settings_text, reply_markup=kb.as_markup())
        else:
            await message.answer(LANGUAGES[user_lang]['admin_only'])

async def process_howto(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    howto_message = LANGUAGES[user_lang]['help']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(howto_message, reply_markup=kb.as_markup())

async def cmd_help(message: Message):
    user_data.update_user_data(message.from_user.id)
    user_lang = user_data.get_user_language(message.from_user.id)
    
    howto_message = LANGUAGES[user_lang]['help']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang].get('delete_button', "Delete"), callback_data="delete_conversion")
    kb.adjust(1)
    
    await message.reply(
        text=howto_message,
        reply_markup=kb.as_markup()
    )

async def process_feedback(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    feedback_message = LANGUAGES[user_lang]['feedback']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(feedback_message, reply_markup=kb.as_markup())

async def process_settings(callback_query_or_message: Union[CallbackQuery, Message], state: FSMContext):
    if isinstance(callback_query_or_message, Message):
        await cmd_settings(callback_query_or_message)
        return
        
    callback_query = callback_query_or_message
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    use_quote = user_data.get_user_quote_format(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
    kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
    kb.adjust(2, 2, 1, 1)
    
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())

async def cmd_price(message: Message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            kb = InlineKeyboardBuilder()
            for i, crypto in enumerate(['BTC', 'ETH', 'BNB', 'SOL', 'TON', 'NOT']):
                kb.button(text=f"{crypto}", callback_data=f"price_select_{crypto}")
            kb.adjust(3)
            
            await message.answer(
                "💰 **Выберите криптовалюту для просмотра графика:**\n\n" +
                "Или используйте формат: `/price BTC`\n" +
                f"Доступные: {', '.join(CRYPTO_CURRENCIES)}",
                reply_markup=kb.as_markup(),
                parse_mode="Markdown"
            )
            return
            
        crypto = parts[1].upper()
        if crypto not in CRYPTO_CURRENCIES:
            await message.answer(
                f"❌ Неподдерживаемая криптовалюта: {crypto}\n" +
                f"✅ Доступные: {', '.join(CRYPTO_CURRENCIES)}"
            )
            return
        
        loading_msg = await message.answer("📊 Загружаю график...")
        
        await send_crypto_chart(message, crypto, "7d", loading_msg)
        
    except Exception as e:
        logger.error(f"Error in cmd_price: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса.")

async def send_crypto_chart(message: Message, crypto: str, period: str = "7d", loading_msg: Message = None):
    try:
        if crypto == 'USDT':
            if loading_msg:
                await loading_msg.delete()
                
            kb = InlineKeyboardBuilder()
            kb.button(text="🗑 Удалить", callback_data="delete_conversion")
            kb.adjust(1)
            
            await message.answer(
                "💰 **USDT/USD**\n\n" +
                "💵 Цена: $1.00\n" +
                "ℹ️ USDT является стейблкоином, привязанным к доллару США\n" +
                "📊 График недоступен для стейблкоинов",
                reply_markup=kb.as_markup(),
                parse_mode="Markdown"
            )
            return

        current_price, price_change = await get_current_price(crypto)
        if current_price is None:
            if loading_msg:
                await loading_msg.edit_text("❌ Не удалось получить данные. Попробуйте позже.")
            return

        chart_image = await create_crypto_chart(crypto, period)
        
        if chart_image:
            kb = InlineKeyboardBuilder()
            periods = [
                ("📊 24ч", "1d"),
                ("📈 7д", "7d"),
                ("📉 30д", "30d")
            ]
            
            for text, p in periods:
                if p == period:
                    text = "✅ " + text
                kb.button(text=text, callback_data=f"price_chart_{crypto}_{p}")
            
            kb.button(text="🔄 Обновить", callback_data=f"price_chart_{crypto}_{period}")
            kb.button(text="🗑 Удалить", callback_data="delete_conversion")
            kb.adjust(3, 1, 1)
            
            period_names = {'1d': '24 часа', '7d': '7 дней', '30d': '30 дней'}
            caption = (
                f"💰 **{crypto}/USDT**\n\n" +
                f"📊 График за {period_names.get(period, period)}\n" +
                f"💵 Текущая цена: ${current_price:,.4f}\n" +
                f"{'📈' if price_change >= 0 else '📉'} Изменение: {price_change:+.2f}%\n\n" +
                f"⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            if loading_msg:
                await loading_msg.delete()
                
            await message.answer_photo(
                photo=BufferedInputFile(chart_image, filename=f"{crypto}_chart.png"),
                caption=caption,
                reply_markup=kb.as_markup(),
                parse_mode="Markdown"
            )
        else:
            if loading_msg:
                await loading_msg.delete()
                
            await process_crypto_price(message, crypto, period)
            
    except Exception as e:
        logger.error(f"Error in send_crypto_chart: {e}")
        if loading_msg:
            await loading_msg.edit_text("❌ Произошла ошибка при создании графика.")

async def process_price_chart_callback(callback_query: CallbackQuery):
    try:
        parts = callback_query.data.split('_')
        
        if parts[1] == 'select':
            crypto = parts[2]
            await callback_query.message.delete()
            loading_msg = await callback_query.message.chat.send_message("📊 Загружаю график...")
            
            class FakeMessage:
                def __init__(self, chat):
                    self.chat = chat
                    
                async def answer(self, *args, **kwargs):
                    return await self.chat.send_message(*args, **kwargs)
                    
                async def answer_photo(self, *args, **kwargs):
                    return await self.chat.send_photo(*args, **kwargs)
            
            fake_message = FakeMessage(callback_query.message.chat)
            await send_crypto_chart(fake_message, crypto, "7d", loading_msg)
            await callback_query.answer()
            return
        
        if parts[1] == 'chart':
            _, _, crypto, period = callback_query.data.split('_')
            
            chat = callback_query.message.chat
            
            await callback_query.message.delete()
            
            loading_msg = await chat.send_message("📊 Обновляю график...")
            
            class FakeMessage:
                def __init__(self, chat):
                    self.chat = chat
                    
                async def answer(self, *args, **kwargs):
                    return await self.chat.send_message(*args, **kwargs)
                    
                async def answer_photo(self, *args, **kwargs):
                    return await self.chat.send_photo(*args, **kwargs)
            
            fake_message = FakeMessage(chat)
            await send_crypto_chart(fake_message, crypto, period, loading_msg)
            
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in price chart callback: {e}")
        await callback_query.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)

async def process_crypto_price(message: Message, crypto: str, period: str):
    try:
        current_price, price_24h_change = await get_current_price(crypto)
        if current_price is None:
            await message.answer("❌ Не удалось получить данные. Попробуйте позже.")
            return

        history_data = await get_crypto_history(crypto, period.replace('d', ''))
        if history_data and history_data['prices']:
            first_price = history_data['prices'][0][1]
            last_price = history_data['prices'][-1][1]
            period_change = ((last_price - first_price) / first_price) * 100
            
            price_info = (
                f"💰 **{crypto}/USDT**\n\n" +
                f"💵 Цена: ${current_price:.4f}\n" +
                f"{'📈' if price_24h_change >= 0 else '📉'} 24ч: {price_24h_change:+.2f}%\n" +
                f"{'📈' if period_change >= 0 else '📉'} {period.replace('d', '')}д: {period_change:+.2f}%"
            )
        else:
            price_info = (
                f"💰 **{crypto}/USDT**\n\n" +
                f"💵 Цена: ${current_price:.4f}\n" +
                f"{'📈' if price_24h_change >= 0 else '📉'} 24ч: {price_24h_change:+.2f}%"
            )

        kb = InlineKeyboardBuilder()
        kb.button(text="📊 График", callback_data=f"price_chart_{crypto}_7d")
        kb.button(text="🗑 Удалить", callback_data="delete_conversion")
        kb.adjust(1)

        await message.answer(
            price_info,
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in process_crypto_price: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса.")

async def process_support(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    support_message = LANGUAGES[user_lang]['support_message']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['donate_button'], url="https://boosty.to/onlive/donate")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(support_message, reply_markup=kb.as_markup())

async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    user_lang = user_data.get_user_language(message.from_user.id)
    stats = user_data.get_statistics()
    stats_message = (
        f"{LANGUAGES[user_lang]['stats_title']}\n\n"
        f"{LANGUAGES[user_lang]['total_users']} {stats['total_users']}\n"
        f"{LANGUAGES[user_lang]['active_users']} {stats['active_today']}\n"
        f"{LANGUAGES[user_lang]['new_users']} {stats['new_today']}"
    )

    await message.answer(stats_message)

async def handle_conversion(message: Message):
    user_data.update_user_data(message.from_user.id)
    user_lang = user_data.get_user_language(message.from_user.id)
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError(LANGUAGES[user_lang]['invalid_input'])
        
        amount = float(parts[0])
        from_currency = parts[1].upper()

        user_currencies = user_data.get_user_currencies(message.from_user.id)
        user_crypto = user_data.get_user_crypto(message.from_user.id)

        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return

        response = f"{amount:.2f} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        
        response += f"{LANGUAGES[user_lang]['fiat_currencies']}\n"
        for to_cur in user_currencies:
            if to_cur != from_currency:
                converted = convert_currency(amount, from_currency, to_cur, rates)
                response += f"{converted:.2f} {ALL_CURRENCIES[to_cur]} {to_cur}\n"
        
        response += "\n"

        response += f"{LANGUAGES[user_lang]['cryptocurrencies_output']}\n"
        for to_cur in user_crypto:
            if to_cur != from_currency:
                converted = convert_currency(amount, from_currency, to_cur, rates)
                response += f"{converted:.8f} {ALL_CURRENCIES[to_cur]} {to_cur}\n"

        logger.info(f"Successful conversion for user {message.from_user.id}: {amount} {from_currency}")
        await message.answer(response)
    except ValueError as ve:
        await message.answer(str(ve))
    except Exception as e:
        logger.error(f"Error during conversion for user {message.from_user.id}: {str(e)}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def inline_query_handler(query: InlineQuery):
    user_data.update_user_data(query.from_user.id)
    user_lang = user_data.get_user_language(query.from_user.id)
    use_quote = user_data.get_user_quote_format(query.from_user.id)
    
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
        await query.answer(results=[empty_input_result], cache_time=1)
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
        await query.answer(results=[error_result], cache_time=1)
        return

    try:
        user_currencies = user_data.get_user_currencies(query.from_user.id)
        user_crypto = user_data.get_user_crypto(query.from_user.id)

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
            await query.answer(results=[no_currency_result], cache_time=1)
            return

        result_content = f"{format_large_number(amount)} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        
        if user_currencies:
            result_content += f"<b>{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}</b>\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    converted = convert_currency(amount, from_currency, to_cur, rates)
                    result_content += f"{format_large_number(converted)} {ALL_CURRENCIES[to_cur]} {to_cur}\n"
            if use_quote:
                result_content += "</blockquote>"
            result_content += "\n"

        if user_crypto:
            result_content += f"<b>{LANGUAGES[user_lang].get('cryptocurrencies_output', 'Cryptocurrencies')}</b>\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    converted = convert_currency(amount, from_currency, to_cur, rates)
                    result_content += f"{format_large_number(converted, True)} {ALL_CURRENCIES[to_cur]}\n"
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
        await query.answer(results=[result], cache_time=1)
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
        await query.answer(results=[error_result], cache_time=1)
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
        await query.answer(results=[error_result], cache_time=1)

async def handle_all_messages(message: types.Message, bot: Bot):
    logger.info(f"Received message: {message.text} from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"Message content: {message.model_dump_json()}")

    if message.new_chat_members:
        for member in message.new_chat_members:
            if member.id == bot.id:
                user_lang = user_data.get_user_language(message.from_user.id)
                welcome_message = LANGUAGES[user_lang]['welcome_group_message']
                await message.answer(welcome_message)
                logger.info(f"Bot added to chat {message.chat.id}. Welcome message sent.")
                return

async def handle_my_chat_member(event: ChatMemberUpdated, bot: Bot):
    logger.info(f"Bot status changed in chat {event.chat.id}")
    logger.info(f"Event content: {event.model_dump_json()}")
    
    if event.new_chat_member.status == "member":
        user_data.initialize_chat_settings(event.chat.id)
        
        user_lang = user_data.get_user_language(event.from_user.id)
        
        welcome_message = LANGUAGES[user_lang]['welcome_group_message']
        
        await bot.send_message(event.chat.id, welcome_message)
        logger.info(f"Welcome message sent to chat {event.chat.id}")

async def handle_message(message: types.Message):
    logger.info(f"Received message: {message.text} from user {message.from_user.id} in chat {message.chat.id}")
    
    if message.text is None:
        logger.info(f"Received message without text from user {message.from_user.id} in chat {message.chat.id}")
        return

    user_id = message.from_user.id
    user_data.update_user_data(user_id)
    user_lang = user_data.get_user_language(user_id)

    if message.text.startswith('/'):
        return 

    separators = [
        r'\s+и\s+', r'\s+and\s+', r'\s+а\s+также\s+', 
        r';', r'\n', r',\s+(?=\d)', r'\s+\+\s+'
    ]
    
    separator_pattern = '|'.join(separators)
    
    parts = re.split(f'({separator_pattern})', message.text, flags=re.IGNORECASE)
    
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
            valid_requests.append(parsed_result)
    
    if valid_requests:
        if len(valid_requests) > 1:
            await process_multiple_conversions(message, valid_requests)
        else:
            amount, currency = valid_requests[0]
            await process_conversion(message, amount, currency)
    else:
        if any(word in message.text.lower() for word in ['конвертировать', 'перевести', 'convert', 'сколько']):
            kb = InlineKeyboardBuilder()
            kb.button(text="❓ Помощь", callback_data="howto")
            kb.adjust(1)
            
            await message.reply(
                f"❌ Не удалось распознать сумму и валюту.\n\n"
                f"Попробуйте написать в формате:\n"
                f"• 100 USD\n"
                f"• 50 евро\n"
                f"• 1000 рублей\n"
                f"• 10к долларов",
                reply_markup=kb.as_markup()
            )
        
        logger.info(f"No valid conversion requests found in message: {message.text} from user {user_id}")

async def process_multiple_conversions(message: types.Message, requests: List[Tuple[float, str]]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data.update_user_data(user_id)
    user_lang = user_data.get_user_language(user_id)
    
    try:
        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return
        
        if message.chat.type in ['group', 'supergroup']:
            user_currencies = user_data.get_chat_currencies(chat_id)
            user_crypto = user_data.get_chat_crypto(chat_id)
        else:
            user_currencies = user_data.get_user_currencies(user_id)
            user_crypto = user_data.get_user_crypto(user_id)
        
        final_response = ""
        
        for amount, from_currency in requests:
            if amount <= 0 or amount > 1e100 or amount < -1e100:
                continue
            
            response = f"{format_large_number(amount)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n"
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
            
            response += "<blockquote expandable>" + "\n\n".join(conversion_parts) + "</blockquote>\n\n"
            final_response += response
        
        if final_response:
            kb = InlineKeyboardBuilder()
            kb.button(text=LANGUAGES[user_lang].get('delete_button', "Delete"), callback_data="delete_conversion")
            
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
    user_lang = user_data.get_user_language(user_id)
    
    try:
        if amount <= 0:
            await message.answer(LANGUAGES[user_lang].get('negative_or_zero_amount'))
            return

        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return
        
        if message.chat.type in ['group', 'supergroup']:
            user_currencies = user_data.get_chat_currencies(chat_id)
            user_crypto = user_data.get_chat_crypto(chat_id)
        else:
            user_currencies = user_data.get_user_currencies(user_id)
            user_crypto = user_data.get_user_crypto(user_id)
        
        response_parts = []
        response_parts.append(f"{format_large_number(amount)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n")
        
        if user_currencies:
            response_parts.append(f"\n{LANGUAGES[user_lang]['fiat_currencies']}")
            fiat_conversions = []
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
                        fiat_conversions.append(conversion_line)
                    except KeyError:
                        continue
            response_parts.append("<blockquote expandable>" + "\n".join(fiat_conversions) + "</blockquote>")
        
        if user_crypto:
            response_parts.append(f"\n\n{LANGUAGES[user_lang]['cryptocurrencies_output']}")
            crypto_conversions = []
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted, True)} {to_cur}"
                        crypto_conversions.append(conversion_line)
                    except KeyError:
                        continue
            response_parts.append("<blockquote expandable>" + "\n".join(crypto_conversions) + "</blockquote>")
        
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang].get('delete_button', "Delete"), callback_data="delete_conversion")
        
        final_response = "".join(response_parts).strip()
        
        await message.reply(
            text=final_response,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in process_conversion for user {user_id}: {e}")
        await message.answer(LANGUAGES[user_lang]['error'])

async def process_about(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    about_message = f"{LANGUAGES[user_lang]['about_message']}\n\n" \
                    f"{LANGUAGES[user_lang]['current_version']} {CURRENT_VERSION}"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['view_changelog'], callback_data='view_changelog')
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(about_message, reply_markup=kb.as_markup())

async def view_changelog(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    changelog = read_changelog()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='about')
    
    await callback_query.message.edit_text(changelog, reply_markup=kb.as_markup())

async def back_to_main(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['news_button'], url="https://t.me/OTC_InfoHub")
    kb.button(text=LANGUAGES[user_lang]['help_button'], callback_data='howto')
    kb.button(text=LANGUAGES[user_lang]['feedback_button'], callback_data='feedback')
    kb.button(text=LANGUAGES[user_lang]['settings_button'], callback_data='settings')
    kb.button(text=LANGUAGES[user_lang]['about_button'], callback_data='about')
    kb.button(text=LANGUAGES[user_lang]['support_button'], callback_data='support')
    kb.adjust(2, 2, 1, 1)
    welcome_message = LANGUAGES[user_lang]['welcome']
    await callback_query.message.edit_text(welcome_message, reply_markup=kb.as_markup())

async def back_to_settings(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    use_quote = user_data.get_user_quote_format(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
    kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
    kb.adjust(2, 2, 1, 1)
    
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())

async def process_callback(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[0]
    
    if action == 'howto':
        await process_howto(callback_query)
    elif action == 'feedback':
        await process_feedback(callback_query)
    elif action == 'settings':
        await process_settings(callback_query, state)
    elif action == 'show':
        if 'currencies' in callback_query.data:
            await show_currencies(callback_query)
        elif 'crypto' in callback_query.data:
            await show_crypto(callback_query)
    elif action == 'toggle':
        if callback_query.data.startswith('toggle_chat_quote_format'):
            await toggle_quote_format(callback_query)
        elif callback_query.data == 'toggle_quote_format':
            await toggle_quote_format(callback_query)
        elif 'currency' in callback_query.data:
            await toggle_currency(callback_query)
        elif 'crypto' in callback_query.data:
            await toggle_crypto(callback_query)
    elif action == 'save':
        if 'chat' in callback_query.data:
            await save_chat_settings(callback_query)
        else:
            await save_settings(callback_query)
    elif action == 'change':
        await change_language(callback_query)
    elif action == 'set':
        await set_language(callback_query)
    elif action == 'back':
        if 'main' in callback_query.data:
            await back_to_main(callback_query)
        elif 'settings' in callback_query.data:
            if 'chat' in callback_query.data:
                await back_to_chat_settings(callback_query)
            else:
                await back_to_settings(callback_query)
    elif action == 'about':
        await process_about(callback_query)
    elif action == 'view':
        await view_changelog(callback_query)
    elif action == 'delete':
        if callback_query.data == 'delete_conversion':
            await delete_conversion_message(callback_query)
    elif action == 'support':
        await process_support(callback_query)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_price, Command("price"))
    dp.message.register(handle_message)
    dp.message.register(handle_conversion)
    dp.message.register(handle_all_messages)
    dp.edited_message.register(handle_message)
    
    dp.callback_query.register(process_howto, F.data == "howto")
    dp.callback_query.register(process_feedback, F.data == "feedback")
    dp.callback_query.register(process_settings, F.data == "settings")
    dp.callback_query.register(process_support, F.data == "support")
    dp.callback_query.register(show_currencies, F.data.startswith("show_currencies_"))
    dp.callback_query.register(show_crypto, F.data == "show_crypto")
    dp.callback_query.register(toggle_currency, F.data.startswith("toggle_currency_"))
    dp.callback_query.register(toggle_crypto, F.data.startswith("toggle_crypto_"))
    dp.callback_query.register(save_settings, F.data == "save_settings")
    dp.callback_query.register(change_language, F.data == "change_language")
    dp.callback_query.register(set_language, F.data.startswith("set_language_"))
    dp.callback_query.register(back_to_main, F.data == "back_to_main")
    dp.callback_query.register(process_about, F.data == "about")
    dp.callback_query.register(view_changelog, F.data == "view_changelog")
    dp.callback_query.register(toggle_quote_format, F.data == "toggle_quote_format")
    
    dp.callback_query.register(show_chat_currencies, F.data.startswith("show_chat_currencies_"))
    dp.callback_query.register(show_chat_crypto, F.data.startswith("show_chat_crypto_"))
    dp.callback_query.register(toggle_chat_currency, F.data.startswith("toggle_chat_currency_"))
    dp.callback_query.register(toggle_chat_crypto, F.data.startswith("toggle_chat_crypto_"))
    dp.callback_query.register(save_chat_settings, F.data.startswith("save_chat_settings_"))
    dp.callback_query.register(back_to_settings, F.data == "back_to_settings")
    dp.callback_query.register(back_to_chat_settings, F.data.startswith("back_to_chat_settings_"))
    dp.callback_query.register(delete_conversion_message, F.data == "delete_conversion")
    dp.callback_query.register(process_price_chart_callback, F.data.startswith("price_chart_"))
    dp.callback_query.register(process_price_chart_callback, F.data.startswith("price_select_"))
    dp.callback_query.register(process_callback)
    
    dp.inline_query.register(inline_query_handler)
    dp.my_chat_member.register(handle_my_chat_member)
    
    await setup_telegram_logging(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())