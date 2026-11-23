import logging
from typing import Any, Dict, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from config import config as app_config
from config.config import (
    CALLBACK_QUERY_MODE,
    INLINE_QUERY_PLACEHOLDER,
    SYNC_BOT_SETTINGS,
)

logger = logging.getLogger(__name__)


async def check_bot_diagnostics(bot: Bot) -> Dict[str, Any]:
    """Read BotFullInfo via bot.me() and return key capability flags."""
    me = await bot.me()
    return {
        "username": me.username,
        "active_usernames": list(me.active_usernames) if me.active_usernames else ([me.username] if me.username else []),
        "can_join_groups": bool(me.can_join_groups),
        "can_read_all_group_messages": bool(me.can_read_all_group_messages),
        "supports_inline_queries": bool(me.supports_inline_queries),
        "inline_query_placeholder": me.inline_query_placeholder,
        "supports_guest_queries": bool(me.supports_guest_queries),
    }


async def sync_bot_settings(bot: Bot) -> Optional[Dict[str, Any]]:
    """Sync Bot API 10.5 settings and ephemeral group commands, then inspect diagnostics."""
    if SYNC_BOT_SETTINGS:
        try:
            await bot.set_my_settings(
                supports_inline_queries=True,
                inline_query_placeholder=INLINE_QUERY_PLACEHOLDER,
                can_join_groups=True,
                can_read_all_group_messages=True,
                callback_query_mode=CALLBACK_QUERY_MODE,
            )
        except TelegramAPIError as e:
            logger.warning("Failed to sync bot settings via setMySettings: %s", e)

        try:
            private_commands = [
                BotCommand(command="start", description="Main menu / Главное меню"),
                BotCommand(command="settings", description="Preferences / Настройки"),
                BotCommand(command="help", description="Usage guide / Справка"),
            ]
            if app_config.ENABLE_WIDGET_CALC:
                private_commands.insert(
                    1,
                    BotCommand(command="calc", description="Calculator widget / Калькулятор"),
                )
            await bot.set_my_commands(
                commands=private_commands,
                scope=BotCommandScopeAllPrivateChats(),
            )
            await bot.set_my_commands(
                commands=[
                    BotCommand(command="settings", description="Chat preferences / Настройки чата", is_ephemeral=True),
                    BotCommand(command="help", description="Usage guide / Справка", is_ephemeral=True),
                ],
                scope=BotCommandScopeAllGroupChats(),
            )
        except TelegramAPIError as e:
            logger.warning("Failed to sync bot command menus: %s", e)

    try:
        diag = await check_bot_diagnostics(bot)
    except TelegramAPIError as e:
        logger.warning("Failed to fetch bot diagnostics via getMe: %s", e)
        return None

    if not diag["can_read_all_group_messages"]:
        logger.warning(
            "Bot privacy mode is ON (can_read_all_group_messages=False); "
            "free-text conversions in group chats will not be delivered."
        )
    if not diag["supports_inline_queries"]:
        logger.warning("Inline mode is disabled on bot (@%s)", diag["username"])

    logger.info(
        "Bot @%s diagnostics: groups=%s privacy_off=%s inline=%s guest=%s",
        diag["username"],
        diag["can_join_groups"],
        diag["can_read_all_group_messages"],
        diag["supports_inline_queries"],
        diag["supports_guest_queries"],
    )
    return diag
