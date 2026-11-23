from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config as app_config
from config.config import CURRENT_VERSION
from config.languages import LANGUAGES
from handlers.widget import send_calculator_widget
from loader import user_data
from utils.button_styles import EMOJI, danger_button, primary_button, success_button
from utils.formatter import read_changelog
from utils.keyboards import build_settings_kb, format_settings_text
from utils.utils import delete_conversion_message, reply_ephemeral_or_fallback

router = Router()


def build_main_menu_kb(user_lang):
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[user_lang]['news_button'], url="https://t.me/OTC_InfoHub", emoji=EMOJI['news']))
    kb.row(
        primary_button(LANGUAGES[user_lang]['help_button'], 'howto', emoji=EMOJI['help']),
        primary_button(LANGUAGES[user_lang]['feedback_button'], 'feedback', emoji=EMOJI['feedback'])
    )
    if app_config.ENABLE_WIDGET_CALC:
        kb.row(
            success_button(LANGUAGES[user_lang]['settings_button'], 'settings', emoji=EMOJI['settings']),
            primary_button(LANGUAGES[user_lang]['calc_button'], 'open_calc')
        )
    else:
        kb.row(
            success_button(LANGUAGES[user_lang]['settings_button'], 'settings', emoji=EMOJI['settings'])
        )
    kb.row(
        success_button(LANGUAGES[user_lang]['about_button'], 'about', emoji=EMOJI['about']),
        success_button(LANGUAGES[user_lang]['support_button'], 'support', emoji=EMOJI['support'])
    )
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
async def cmd_start(message: Message, command: CommandObject | None = None):
    from_user = message.from_user
    if from_user is None:
        return

    await user_data.update_user_data(from_user.id, language_code=from_user.language_code)
    user_lang = await user_data.get_user_language(from_user.id)

    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_lang = await user_data.get_chat_language(message.chat.id)
        await message.answer(
            LANGUAGES[chat_lang].get(
                'welcome_group_message',
                LANGUAGES[chat_lang].get('welcome', LANGUAGES['en']['welcome'])
            )
        )
        return

    deep_link = (command.args or '').strip().lower() if command else ''
    if deep_link == 'settings':
        display_format = await user_data.get_user_display_format(from_user.id)
        kb = build_settings_kb(user_lang)
        await message.answer(
            format_settings_text(user_lang, display_format),
            reply_markup=kb.as_markup(),
        )
        return
    if deep_link == 'calc':
        await send_calculator_widget(message)
        return

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
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        lang_code = await user_data.get_chat_language(message.chat.id)
    else:
        lang_code = await user_data.get_user_language(from_user.id)

    kb = InlineKeyboardBuilder()
    kb.row(danger_button(LANGUAGES[lang_code].get('delete_button', "Delete"), "delete_conversion", emoji=EMOJI['delete']))

    await reply_ephemeral_or_fallback(message, LANGUAGES[lang_code]['help'], reply_markup=kb.as_markup())


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
