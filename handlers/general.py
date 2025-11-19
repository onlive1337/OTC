from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import CURRENT_VERSION
from config.languages import LANGUAGES
from loader import user_data
from utils.utils import read_changelog, delete_conversion_message

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await user_data.update_user_data(message.from_user.id)
    
    user_lang = await user_data.get_user_language(message.from_user.id)
    
    if message.chat.type in ['group', 'supergroup']:
        chat_member = await message.chat.get_member(message.from_user.id)
        if chat_member.status in ['creator', 'administrator']:
            from data.chat_settings import show_chat_settings
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

@router.callback_query(F.data == "howto")
async def process_howto(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    
    howto_message = LANGUAGES[user_lang]['help']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(howto_message, reply_markup=kb.as_markup())

@router.message(Command("help"))
async def cmd_help(message: Message):
    await user_data.update_user_data(message.from_user.id)
    user_lang = await user_data.get_user_language(message.from_user.id)
    
    howto_message = LANGUAGES[user_lang]['help']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang].get('delete_button', "Delete"), callback_data="delete_conversion")
    kb.adjust(1)
    
    await message.reply(
        text=howto_message,
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "feedback")
async def process_feedback(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    feedback_message = LANGUAGES[user_lang]['feedback']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(feedback_message, reply_markup=kb.as_markup())

@router.callback_query(F.data == "support")
async def process_support(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    
    support_message = LANGUAGES[user_lang]['support_message']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['donate_button'], url="https://boosty.to/onlive/donate")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(support_message, reply_markup=kb.as_markup())

@router.callback_query(F.data == "about")
async def process_about(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    
    about_message = f"{LANGUAGES[user_lang]['about_message']}\n\n" \
                    f"{LANGUAGES[user_lang]['current_version']} {CURRENT_VERSION}"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['view_changelog'], callback_data='view_changelog')
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(about_message, reply_markup=kb.as_markup())

@router.callback_query(F.data == "view_changelog")
async def view_changelog(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    
    changelog = read_changelog()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='about')
    
    await callback_query.message.edit_text(changelog, reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback_query: CallbackQuery):
    await user_data.update_user_data(callback_query.from_user.id)
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
    
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

@router.callback_query(F.data == "delete_conversion")
async def delete_conversion_handler(callback_query: CallbackQuery):
    await delete_conversion_message(callback_query)
