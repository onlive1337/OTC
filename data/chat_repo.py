import asyncio
from collections import OrderedDict
import logging
import sqlite3
from typing import Any, List, Protocol

import aiosqlite
from aiosqlite import IntegrityError

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from utils.formatter import flags_for_display_format, resolve_display_format

logger = logging.getLogger(__name__)


class _ChatRepoDeps(Protocol):
    chat_data: OrderedDict[int, dict[str, Any]]
    _write_lock: asyncio.Lock

    async def _ensure_chat(self, chat_id: int): ...
    async def _get_read_conn(self) -> aiosqlite.Connection: ...
    async def _get_write_conn(self) -> aiosqlite.Connection: ...
    def _touch_chat_cache(self, chat_id: int) -> None: ...
    def _set_chat_cache(self, chat_id: int, value: dict[str, Any]) -> None: ...
    def _cleanup_cache_if_needed(self) -> None: ...
    def _set_chat_field(self, chat_id: int, field: str, value: Any) -> None: ...
    async def get_chat_quote_format(self, chat_id: int) -> bool: ...
    async def get_chat_rich_format(self, chat_id: int) -> bool: ...


class ChatRepoMixin:
    def _set_chat_field(self: _ChatRepoDeps, chat_id: int, field: str, value: Any) -> None:
        if chat_id not in self.chat_data or not isinstance(self.chat_data[chat_id], dict):
            self._set_chat_cache(chat_id, {field: value})
            return
        self.chat_data[chat_id][field] = value
        self._touch_chat_cache(chat_id)

    async def _ensure_chat(self: _ChatRepoDeps, chat_id: int):
        if chat_id in self.chat_data:
            self._touch_chat_cache(chat_id)
            return

        async with self._write_lock:
            if chat_id in self.chat_data:
                self._touch_chat_cache(chat_id)
                return
            conn = await self._get_write_conn()
            async with conn.execute("SELECT chat_id FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
                if await cursor.fetchone() is not None:
                    self._set_chat_cache(chat_id, {})
                    return
            default_currencies = ACTIVE_CURRENCIES[:5]
            default_crypto = CRYPTO_CURRENCIES[:5]
            try:
                await conn.execute("INSERT INTO chats(chat_id, quote_format, language, rich_format) VALUES(?, 0, 'en', 0)", (chat_id,))
                currencies_data = [(chat_id, c) for c in default_currencies]
                await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", currencies_data)
                crypto_data = [(chat_id, s) for s in default_crypto]
                await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", crypto_data)
                await conn.commit()
                self._set_chat_cache(chat_id, {
                    'currencies': list(default_currencies),
                    'crypto': list(default_crypto),
                    'quote_format': False,
                    'language': 'en',
                    'rich_format': False,
                })
            except IntegrityError:
                logger.debug("Chat %s already exists (race condition handled)", chat_id)
            except sqlite3.Error:
                logger.exception("Error registering chat %s", chat_id)

    async def get_chat_data(self: _ChatRepoDeps, chat_id: int) -> dict:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'currencies' in cached and 'language' in cached:
            self._touch_chat_cache(chat_id)
            return cached

        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()

        async with conn.execute("""
            SELECT 
                c.quote_format, c.language, c.rich_format,
                (SELECT GROUP_CONCAT(currency) FROM chat_currencies WHERE chat_id = c.chat_id) as currencies,
                (SELECT GROUP_CONCAT(symbol) FROM chat_crypto WHERE chat_id = c.chat_id) as crypto
            FROM chats c WHERE c.chat_id = ?
        """, (chat_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return {'currencies': [], 'crypto': [], 'quote_format': False, 'language': 'en', 'rich_format': False}

        quote_format, language, rich_format, currencies_str, crypto_str = row
        currencies = currencies_str.split(',') if currencies_str else []
        crypto = crypto_str.split(',') if crypto_str else []

        data = {
            'currencies': currencies,
            'crypto': crypto,
            'quote_format': bool(quote_format) if quote_format else False,
            'language': language or 'en',
            'rich_format': bool(rich_format) if rich_format else False,
        }
        self._set_chat_cache(chat_id, data)
        return data

    async def initialize_chat_settings(self: _ChatRepoDeps, chat_id: int):
        await self._ensure_chat(chat_id)
        logger.info(f"Initialized settings for chat {chat_id}")

    def update_chat_cache(self: _ChatRepoDeps, chat_id: int):
        self.chat_data.pop(chat_id, None)
        logger.debug(f"Invalidated chat cache for chat {chat_id}")

    async def get_chat_quote_format(self: _ChatRepoDeps, chat_id: int) -> bool:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'quote_format' in cached:
            self._touch_chat_cache(chat_id)
            return cached['quote_format']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        result = bool(row[0]) if row else False
        self._set_chat_field(chat_id, 'quote_format', result)
        return result

    async def set_chat_quote_format(self: _ChatRepoDeps, chat_id: int, use_quote: bool):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            if use_quote:
                await conn.execute(
                    "UPDATE chats SET quote_format=1, rich_format=0 WHERE chat_id=?",
                    (chat_id,),
                )
            else:
                await conn.execute(
                    "UPDATE chats SET quote_format=0 WHERE chat_id=?",
                    (chat_id,),
                )
            await conn.commit()
        if chat_id in self.chat_data and isinstance(self.chat_data[chat_id], dict):
            self._set_chat_field(chat_id, 'quote_format', use_quote)
            if use_quote:
                self._set_chat_field(chat_id, 'rich_format', False)

    async def get_chat_rich_format(self: _ChatRepoDeps, chat_id: int) -> bool:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'rich_format' in cached:
            self._touch_chat_cache(chat_id)
            return cached['rich_format']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT rich_format FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        result = bool(row[0]) if row else False
        self._set_chat_field(chat_id, 'rich_format', result)
        return result

    async def set_chat_rich_format(self: _ChatRepoDeps, chat_id: int, use_rich: bool):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            if use_rich:
                await conn.execute(
                    "UPDATE chats SET rich_format=1, quote_format=0 WHERE chat_id=?",
                    (chat_id,),
                )
            else:
                await conn.execute(
                    "UPDATE chats SET rich_format=0 WHERE chat_id=?",
                    (chat_id,),
                )
            await conn.commit()
        if chat_id in self.chat_data and isinstance(self.chat_data[chat_id], dict):
            self._set_chat_field(chat_id, 'rich_format', use_rich)
            if use_rich:
                self._set_chat_field(chat_id, 'quote_format', False)

    async def get_chat_display_format(self: _ChatRepoDeps, chat_id: int) -> str:
        use_quote = await self.get_chat_quote_format(chat_id)
        use_rich = await self.get_chat_rich_format(chat_id)
        return resolve_display_format(use_quote, use_rich)

    async def set_chat_display_format(self: _ChatRepoDeps, chat_id: int, display_format: str) -> None:
        use_quote, use_rich = flags_for_display_format(display_format)
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute(
                "UPDATE chats SET quote_format=?, rich_format=? WHERE chat_id=?",
                (1 if use_quote else 0, 1 if use_rich else 0, chat_id),
            )
            await conn.commit()
        self._set_chat_field(chat_id, 'quote_format', use_quote)
        self._set_chat_field(chat_id, 'rich_format', use_rich)

    async def get_chat_currencies(self: _ChatRepoDeps, chat_id: int) -> list:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'currencies' in cached:
            self._touch_chat_cache(chat_id)
            return cached['currencies']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        currencies = [r[0] for r in rows]
        self._set_chat_field(chat_id, 'currencies', currencies)
        return currencies

    async def set_chat_currencies(self: _ChatRepoDeps, chat_id: int, currencies: List[str]):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM chat_currencies WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", [(chat_id, c) for c in currencies])
            await conn.commit()
        if chat_id in self.chat_data and isinstance(self.chat_data[chat_id], dict):
            self._set_chat_field(chat_id, 'currencies', currencies)

    async def get_chat_crypto(self: _ChatRepoDeps, chat_id: int) -> list:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'crypto' in cached:
            self._touch_chat_cache(chat_id)
            return cached['crypto']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        crypto = [r[0] for r in rows]
        self._set_chat_field(chat_id, 'crypto', crypto)
        return crypto

    async def set_chat_crypto(self: _ChatRepoDeps, chat_id: int, crypto_list: List[str]):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM chat_crypto WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", [(chat_id, s) for s in crypto_list])
            await conn.commit()
        if chat_id in self.chat_data and isinstance(self.chat_data[chat_id], dict):
            self._set_chat_field(chat_id, 'crypto', crypto_list)

    async def get_chat_language(self: _ChatRepoDeps, chat_id: int) -> str:
        cached = self.chat_data.get(chat_id)
        if isinstance(cached, dict) and 'language' in cached:
            self._touch_chat_cache(chat_id)
            return cached['language']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT language FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        lang = row[0] if row and row[0] else 'en'
        self._set_chat_field(chat_id, 'language', lang)
        return lang

    async def set_chat_language(self: _ChatRepoDeps, chat_id: int, language: str):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE chats SET language=? WHERE chat_id=?", (language, chat_id))
            await conn.commit()
        self._set_chat_field(chat_id, 'language', language)
