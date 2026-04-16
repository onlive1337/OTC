from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import CURRENT_VERSION
from config.languages import LANGUAGES
from loader import user_data
from utils.formatter import read_changelog
from utils.utils import delete_conversion_message
from utils.button_styles import primary_button, success_button, danger_button, EMOJI

router = Router()

def build_main_menu_kb(user_lang):
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[user_lang]['news_button'], url="https://t.me/OTC_InfoHub", emoji=EMOJI['news']))
    kb.row(
        primary_button(LANGUAGES[user_lang]['help_button'], 'howto', emoji=EMOJI['help']),
        primary_button(LANGUAGES[user_lang]['feedback_button'], 'feedback', emoji=EMOJI['feedback'])
    )
    kb.row(
        success_button(LANGUAGES[user_lang]['settings_button'], 'settings', emoji=EMOJI['settings']),
        success_button(LANGUAGES[user_lang]['about_button'], 'about', emoji=EMOJI['about'])
    )
    kb.row(success_button(LANGUAGES[user_lang]['support_button'], 'support', emoji=EMOJI['support']))
    return kb


async def _prepare_callback_user_lang(callback_query: CallbackQuery) -> str:
    from_user = callback_query.from_user
    if from_user is None:
        await callback_query.answer()
        return 'en'

    await user_data.update_user_data(from_user.id)
    await callback_query.answer()
    return await user_data.get_user_language(from_user.id)


def _build_back_to_main_kb(user_lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[user_lang]['back'], 'back_to_main', emoji=EMOJI['back']))
    return kb

@router.message(CommandStart())
async def cmd_start(message: Message):
    from_user = message.from_user
    if from_user is None:
        return

    await user_data.update_user_data(from_user.id, language_code=from_user.language_code)
    user_lang = await user_data.get_user_language(from_user.id)

    if message.chat.type in ['group', 'supergroup']:
        chat_lang = await user_data.get_chat_language(message.chat.id)
        await message.answer(
            LANGUAGES[chat_lang].get(
                'welcome_group_message',
                LANGUAGES[chat_lang].get('welcome', LANGUAGES['en']['welcome'])
            )
        )
    else:
        kb = build_main_menu_kb(user_lang)
        await message.answer(LANGUAGES[user_lang]['welcome'], reply_markup=kb.as_markup())

@router.callback_query(F.data == "howto")
async def process_howto(callback_query: CallbackQuery):
    user_lang = await _prepare_callback_user_lang(callback_query)
    kb = _build_back_to_main_kb(user_lang)

    if not isinstance(callback_query.message, Message):
        return

    await callback_query.message.edit_text(LANGUAGES[user_lang]['help'], reply_markup=kb.as_markup())

@router.message(Command("help"))
async def cmd_help(message: Message):
    from_user = message.from_user
    if from_user is None:
        return

    await user_data.update_user_data(from_user.id)
    user_lang = await user_data.get_user_language(from_user.id)

    kb = InlineKeyboardBuilder()
    kb.row(danger_button(LANGUAGES[user_lang].get('delete_button', "Delete"), "delete_conversion", emoji=EMOJI['delete']))
    
    await message.reply(text=LANGUAGES[user_lang]['help'], reply_markup=kb.as_markup())

@router.callback_query(F.data == "feedback")
async def process_feedback(callback_query: CallbackQuery):
    user_lang = await _prepare_callback_user_lang(callback_query)
    kb = _build_back_to_main_kb(user_lang)

    if not isinstance(callback_query.message, Message):
        return

    await callback_query.message.edit_text(LANGUAGES[user_lang]['feedback'], reply_markup=kb.as_markup())

@router.callback_query(F.data == "support")
async def process_support(callback_query: CallbackQuery):
    user_lang = await _prepare_callback_user_lang(callback_query)

    kb = InlineKeyboardBuilder()
    kb.row(success_button(LANGUAGES[user_lang]['donate_button'], url="https://boosty.to/onlive/donate", emoji=EMOJI['support']))
    kb.row(primary_button(LANGUAGES[user_lang]['back'], 'back_to_main', emoji=EMOJI['back']))

    if not isinstance(callback_query.message, Message):
        return

    await callback_query.message.edit_text(LANGUAGES[user_lang]['support_message'], reply_markup=kb.as_markup())

@router.callback_query(F.data == "about")
async def process_about(callback_query: CallbackQuery):
    user_lang = await _prepare_callback_user_lang(callback_query)

    about_message = f"{LANGUAGES[user_lang]['about_message']}\n\n" \
                    f"{LANGUAGES[user_lang]['current_version']} {CURRENT_VERSION}"
    
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[user_lang]['view_changelog'], 'view_changelog', emoji=EMOJI['changelog']))
    kb.row(primary_button(LANGUAGES[user_lang]['back'], 'back_to_main', emoji=EMOJI['back']))

    if not isinstance(callback_query.message, Message):
        return

    await callback_query.message.edit_text(about_message, reply_markup=kb.as_markup())

@router.callback_query(F.data == "view_changelog")
async def view_changelog(callback_query: CallbackQuery):
    user_lang = await _prepare_callback_user_lang(callback_query)

    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[user_lang]['back'], 'about', emoji=EMOJI['back']))

    if not isinstance(callback_query.message, Message):
        return

    await callback_query.message.edit_text(read_changelog(), reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback_query: CallbackQuery):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None or not isinstance(callback_query.message, Message):
        return

    await user_data.update_user_data(from_user.id)
    user_lang = await user_data.get_user_language(from_user.id)

    kb = build_main_menu_kb(user_lang)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['welcome'], reply_markup=kb.as_markup())

@router.callback_query(F.data == "delete_conversion")
async def delete_conversion_handler(callback_query: CallbackQuery):
    await delete_conversion_message(callback_query)
