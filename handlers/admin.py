import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from config.config import ADMIN_IDS
from config.languages import LANGUAGES
from loader import bot, user_data
from states.states import AdminStates
from utils.middleware import get_metrics
from utils.button_styles import primary_button, success_button, danger_button, EMOJI

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    user_lang = await user_data.get_user_language(message.from_user.id)
    stats = await user_data.get_statistics()
    stats_message = (
        f"{LANGUAGES[user_lang]['stats_title']}\n\n"
        f"{LANGUAGES[user_lang]['total_users']} {stats['total_users']}\n"
        f"{LANGUAGES[user_lang]['active_users']} {stats['active_today']}\n"
        f"{LANGUAGES[user_lang]['new_users']} {stats['new_today']}"
    )

    await message.answer(stats_message)

@router.message(Command("health"))
async def cmd_health(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    metrics = get_metrics()
    stats = await user_data.get_statistics()

    db_ok = "✅"
    try:
        conn = await user_data._get_conn()
        await conn.execute("SELECT 1")
    except Exception:
        db_ok = "❌"

    text = (
        f"🏥 <b>Bot Health</b>\n\n"
        f"⏱ Uptime: {metrics['uptime']}\n"
        f"📨 Requests: {metrics['total_requests']}\n"
        f"❌ Errors: {metrics['total_errors']}\n"
        f"🗄 DB: {db_ok}\n"
        f"👥 Active today: {stats['active_today']}\n"
        f"👤 Total users: {stats['total_users']}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    kb = InlineKeyboardBuilder()
    kb.row(danger_button("❌ Отмена", "broadcast_cancel"))

    await message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям.\n"
        "Поддерживается текст, фото, видео, документ и стикер.\n\n"
        "Для отмены нажмите кнопку ниже.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await state.set_state(AdminStates.waiting_broadcast)


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("❌ Рассылка отменена.")
    await callback_query.answer()


@router.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    msg_data = data.get("broadcast_msg")
    if not msg_data:
        await callback_query.message.edit_text("⚠️ Сообщение не найдено. Попробуйте снова.")
        return

    await callback_query.message.edit_text("📤 Рассылка начата...")
    await callback_query.answer()

    user_ids = await user_data.get_all_user_ids()
    sent, failed, blocked = 0, 0, 0

    sem = asyncio.Semaphore(15)
    
    async def send_wrapper(uid):
        nonlocal sent, failed, blocked
        async with sem:
            while True:
                try:
                    if msg_data["type"] == "text":
                        await bot.send_message(uid, msg_data["text"], parse_mode="HTML")
                    elif msg_data["type"] == "photo":
                        await bot.send_photo(uid, msg_data["file_id"], caption=msg_data.get("caption"), parse_mode="HTML")
                    elif msg_data["type"] == "video":
                        await bot.send_video(uid, msg_data["file_id"], caption=msg_data.get("caption"), parse_mode="HTML")
                    elif msg_data["type"] == "document":
                        await bot.send_document(uid, msg_data["file_id"], caption=msg_data.get("caption"), parse_mode="HTML")
                    elif msg_data["type"] == "sticker":
                        await bot.send_sticker(uid, msg_data["file_id"])
                    sent += 1
                    break
                except TelegramRetryAfter as e:
                    logger.warning("Flood limit for %s, sleeping %ss", uid, e.retry_after)
                    await asyncio.sleep(e.retry_after)
                    continue
                except Exception as e:
                    err_msg = str(e).lower()
                    if any(x in err_msg for x in ["blocked", "deactivated", "not found", "forbidden", "cannot initiate", "entity"]):
                        blocked += 1
                    else:
                        failed += 1
                        logger.warning("Broadcast to %s failed: %s", uid, e)
                    break
            
            await asyncio.sleep(0.05) 

    tasks = [send_wrapper(uid) for uid in user_ids]
    await asyncio.gather(*tasks)

    report = (
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Отправлено: {sent}\n"
        f"🚫 Заблокировали: {blocked}\n"
        f"❌ Ошибки: {failed}\n"
        f"📊 Всего: {len(user_ids)}"
    )
    await callback_query.message.answer(report, parse_mode="HTML")


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    msg_data = {}

    if message.photo:
        msg_data = {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption or ""}
    elif message.video:
        msg_data = {"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}
    elif message.document:
        msg_data = {"type": "document", "file_id": message.document.file_id, "caption": message.caption or ""}
    elif message.sticker:
        msg_data = {"type": "sticker", "file_id": message.sticker.file_id}
    elif message.text:
        msg_data = {"type": "text", "text": message.text}
    else:
        await message.answer("⚠️ Этот тип сообщения не поддерживается. Отправьте текст, фото, видео, документ или стикер.")
        return

    await state.update_data(broadcast_msg=msg_data)

    stats = await user_data.get_statistics()

    kb = InlineKeyboardBuilder()
    kb.row(
        success_button("✅ Отправить", "broadcast_confirm"),
        danger_button("❌ Отмена", "broadcast_cancel")
    )

    preview_text = f"📢 <b>Предпросмотр рассылки</b>\n\nТип: {msg_data['type']}\n👥 Получатели: {stats['total_users']} пользователей\n\nОтправить?"
    await message.answer(preview_text, parse_mode="HTML", reply_markup=kb.as_markup())
