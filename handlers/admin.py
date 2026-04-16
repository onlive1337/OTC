import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError, TelegramForbiddenError, TelegramBadRequest
from config.config import ADMIN_IDS
from config.languages import LANGUAGES
from loader import bot, user_data
from states.states import AdminStates
from utils.middleware import get_metrics
from utils.button_styles import success_button, danger_button

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    from_user = message.from_user
    if from_user is None:
        return

    user_lang = await user_data.get_user_language(from_user.id)
    if from_user.id not in ADMIN_IDS:
        await message.answer(LANGUAGES[user_lang]['no_admin_rights'])
        return

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
    from_user = message.from_user
    if from_user is None:
        return

    user_lang = await user_data.get_user_language(from_user.id)
    if from_user.id not in ADMIN_IDS:
        await message.answer(LANGUAGES[user_lang]['no_admin_rights'])
        return

    metrics = get_metrics()
    stats = await user_data.get_statistics()

    db_ok = "✅" if await user_data.ping_db() else "❌"

    text = (
        f"🏥 <b>Bot Health</b>\n\n"
        f"⏱ Uptime: {metrics['uptime']}\n"
        f"📨 Requests: {metrics['total_requests']}\n"
        f"❌ Errors: {metrics['total_errors']}\n"
        f"🗄 DB: {db_ok}\n"
        f"👥 Active today: {stats['active_today']}\n"
        f"👤 Total users: {stats['total_users']}"
    )
    await message.answer(text)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    from_user = message.from_user
    if from_user is None or from_user.id not in ADMIN_IDS:
        return

    user_lang = await user_data.get_user_language(from_user.id)
    lang = LANGUAGES[user_lang]

    kb = InlineKeyboardBuilder()
    kb.row(danger_button(lang.get("broadcast_cancel_button", "❌ Cancel"), "broadcast_cancel"))

    await message.answer(
        f"{lang.get('broadcast_title', '📢 <b>Broadcast</b>')}\n\n{lang.get('broadcast_prompt')}",
        reply_markup=kb.as_markup()
    )
    await state.set_state(AdminStates.waiting_broadcast)


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback_query: CallbackQuery, state: FSMContext):
    from_user = callback_query.from_user
    if from_user is None:
        await callback_query.answer()
        return

    if not isinstance(callback_query.message, Message):
        await callback_query.answer()
        return

    user_lang = await user_data.get_user_language(from_user.id)
    await state.clear()
    await callback_query.message.edit_text(LANGUAGES[user_lang].get('broadcast_cancelled', '❌ Broadcast canceled.'))
    await callback_query.answer()


@router.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(callback_query: CallbackQuery, state: FSMContext):
    from_user = callback_query.from_user
    if from_user is None:
        await callback_query.answer()
        return

    if not isinstance(callback_query.message, Message):
        await callback_query.answer()
        return

    user_lang = await user_data.get_user_language(from_user.id)
    lang = LANGUAGES[user_lang]
    data = await state.get_data()
    await state.clear()

    msg_data_raw = data.get("broadcast_msg")
    if not isinstance(msg_data_raw, dict):
        await callback_query.message.edit_text(lang.get('broadcast_msg_not_found', '⚠️ Message not found. Please try again.'))
        return

    msg_data = msg_data_raw

    await callback_query.message.edit_text(lang.get('broadcast_started', '📤 Broadcast started...'))
    await callback_query.answer()

    user_ids = await user_data.get_all_user_ids()
    counters = {"sent": 0, "failed": 0, "blocked": 0}
    total = len(user_ids)
    progress_msg: Message = callback_query.message
    broadcast_sem = asyncio.Semaphore(25)

    async def send_one(uid):
        async with broadcast_sem:
            retries = 0
            while True:
                try:
                    if msg_data["type"] == "text":
                        await bot.send_message(uid, msg_data["text"])
                    elif msg_data["type"] == "photo":
                        await bot.send_photo(uid, msg_data["file_id"], caption=msg_data.get("caption"))
                    elif msg_data["type"] == "video":
                        await bot.send_video(uid, msg_data["file_id"], caption=msg_data.get("caption"))
                    elif msg_data["type"] == "document":
                        await bot.send_document(uid, msg_data["file_id"], caption=msg_data.get("caption"))
                    elif msg_data["type"] == "sticker":
                        await bot.send_sticker(uid, msg_data["file_id"])
                    counters["sent"] += 1
                    break
                except TelegramRetryAfter as e:
                    retries += 1
                    if retries > 5:
                        counters["failed"] += 1
                        logger.warning("Broadcast to %s: too many retries", uid)
                        break
                    logger.warning("Flood limit for %s, sleeping %ss", uid, e.retry_after)
                    await asyncio.sleep(e.retry_after)
                    continue
                except TelegramForbiddenError:
                    counters["blocked"] += 1
                    break
                except TelegramBadRequest as e:
                    err_msg = str(e).lower()
                    if any(x in err_msg for x in ["chat not found", "user not found", "forbidden", "cannot initiate"]):
                        counters["blocked"] += 1
                    else:
                        counters["failed"] += 1
                        logger.warning("Broadcast to %s bad request: %s", uid, e)
                    break
                except TelegramAPIError as e:
                    counters["failed"] += 1
                    logger.warning("Broadcast to %s API error: %s", uid, e)
                    break
                except (KeyError, TypeError, ValueError) as send_error:
                    counters["failed"] += 1
                    logger.warning("Broadcast to %s failed: %s", uid, send_error)
                    break
            await asyncio.sleep(0.05)

    BATCH_SIZE = 100
    PROGRESS_EVERY = 500
    processed = 0

    for i in range(0, total, BATCH_SIZE):
        batch = user_ids[i:i + BATCH_SIZE]
        await asyncio.gather(*(send_one(uid) for uid in batch))
        processed += len(batch)

        if processed % PROGRESS_EVERY < BATCH_SIZE and total > PROGRESS_EVERY:
            try:
                await progress_msg.edit_text(
                    lang.get('broadcast_progress', '📤 Broadcasting... {processed}/{total} ({percent}%)').format(
                        processed=processed,
                        total=total,
                        percent=processed * 100 // total,
                    )
                )
            except TelegramAPIError:
                pass

    report = lang.get('broadcast_done', '📢 <b>Broadcast completed</b>\n\n✅ Sent: {sent}\n🚫 Blocked: {blocked}\n❌ Failed: {failed}\n📊 Total: {total}').format(
        sent=counters['sent'],
        blocked=counters['blocked'],
        failed=counters['failed'],
        total=total,
    )
    await progress_msg.edit_text(report)


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext):
    from_user = message.from_user
    if from_user is None or from_user.id not in ADMIN_IDS:
        await state.clear()
        return

    user_lang = await user_data.get_user_language(from_user.id)
    lang = LANGUAGES[user_lang]

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
        await message.answer(lang.get('broadcast_unsupported_type', '⚠️ This message type is not supported.'))
        return

    await state.update_data(broadcast_msg=msg_data)

    stats = await user_data.get_statistics()

    kb = InlineKeyboardBuilder()
    kb.row(
        success_button(lang.get('broadcast_send_button', '✅ Send'), "broadcast_confirm"),
        danger_button(lang.get('broadcast_cancel_button', '❌ Cancel'), "broadcast_cancel")
    )

    preview_text = lang.get('broadcast_preview', '📢 <b>Broadcast Preview</b>\n\nType: {msg_type}\n👥 Recipients: {total_users} users\n\nSend now?').format(
        msg_type=msg_data['type'],
        total_users=stats['total_users'],
    )
    await message.answer(preview_text, reply_markup=kb.as_markup())
