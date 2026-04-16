import logging
from datetime import datetime
from typing import Any, List, Optional, Protocol

import asyncio

import aiosqlite

from aiosqlite import IntegrityError

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES

logger = logging.getLogger(__name__)


class _UserRepoDeps(Protocol):
    user_data: dict[int, dict[str, Any]]
    _write_lock: asyncio.Lock
    _pending_interactions: dict[int, int]
    _pending_last_seen: dict[int, str]

    @staticmethod
    def _detect_language(language_code: Optional[str] = None) -> str: ...
    async def _ensure_user(self, user_id: int, language_code: Optional[str] = None): ...
    async def _get_read_conn(self) -> aiosqlite.Connection: ...
    async def _get_write_conn(self) -> aiosqlite.Connection: ...
    def _cleanup_cache_if_needed(self) -> None: ...


class UserRepoMixin:
    @staticmethod
    def _detect_language(language_code: Optional[str] = None) -> str:
        if not language_code:
            return 'ru'
        cis_codes = ('ru', 'uk', 'be', 'kk', 'uz', 'tg', 'ky')
        return 'ru' if language_code.lower().startswith(cis_codes) else 'en'

    async def _ensure_user(self: _UserRepoDeps, user_id: int, language_code: Optional[str] = None):
        if user_id in self.user_data:
            return

        async with self._write_lock:
            conn = await self._get_write_conn()
            async with conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)) as cursor:
                if await cursor.fetchone() is not None:
                    return
            default_lang = self._detect_language(language_code)
            today = datetime.now().strftime('%Y-%m-%d')
            default_currencies = ACTIVE_CURRENCIES[:5]
            default_crypto = CRYPTO_CURRENCIES[:5]
            try:
                await conn.execute(
                    "INSERT INTO users(user_id, interactions, last_seen, first_seen, language, use_quote_format) VALUES(?, 0, ?, ?, ?, 1)",
                    (user_id, today, today, default_lang)
                )
                currencies_data = [(user_id, c) for c in default_currencies]
                await conn.executemany("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", currencies_data)
                crypto_data = [(user_id, s) for s in default_crypto]
                await conn.executemany("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", crypto_data)
                await conn.commit()
                self.user_data[user_id] = {
                    "interactions": 0,
                    "last_seen": today,
                    "first_seen": today,
                    "selected_currencies": list(default_currencies),
                    "selected_crypto": list(default_crypto),
                    "language": default_lang,
                    "use_quote_format": True,
                }
                logger.info(f"New user {user_id} registered with language '{default_lang}'")
            except IntegrityError:
                logger.debug("User %s already exists (race condition handled)", user_id)
            except Exception as e:
                logger.error(f"Error registering user {user_id}: {e}")

    async def get_user_data(self: _UserRepoDeps, user_id: int) -> dict:
        self._cleanup_cache_if_needed()
        cached = self.user_data.get(user_id)
        if cached and 'selected_currencies' in cached and 'language' in cached:
            return cached
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("""
            SELECT 
                u.interactions, u.last_seen, u.first_seen, u.language, u.use_quote_format,
                (SELECT GROUP_CONCAT(currency) FROM user_currencies WHERE user_id = u.user_id) as currencies,
                (SELECT GROUP_CONCAT(symbol) FROM user_crypto WHERE user_id = u.user_id) as crypto
            FROM users u WHERE u.user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return {}
        interactions, last_seen, first_seen, language, use_quote, currencies_str, crypto_str = row
        currencies = currencies_str.split(',') if currencies_str else []
        crypto = crypto_str.split(',') if crypto_str else []
        data = {
            "interactions": interactions,
            "last_seen": last_seen,
            "selected_currencies": currencies,
            "selected_crypto": crypto,
            "language": language or 'ru',
            "first_seen": first_seen,
            "use_quote_format": bool(use_quote),
        }
        self.user_data[user_id] = data
        return data

    async def update_user_data(self: _UserRepoDeps, user_id: int, language_code: Optional[str] = None):
        await self._ensure_user(user_id, language_code=language_code)
        today = datetime.now().strftime('%Y-%m-%d')
        self._cleanup_cache_if_needed()
        user_cache = self.user_data.get(user_id)
        is_today = user_cache and user_cache.get("last_seen") == today
        self._pending_interactions[user_id] = self._pending_interactions.get(user_id, 0) + 1
        if not is_today:
            self._pending_last_seen[user_id] = today
        if user_cache:
            user_cache["interactions"] = user_cache.get("interactions", 0) + 1
            if not is_today:
                user_cache["last_seen"] = today

    async def get_user_currencies(self: _UserRepoDeps, user_id: int) -> list:
        cached = self.user_data.get(user_id)
        if cached and "selected_currencies" in cached:
            return cached["selected_currencies"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_currencies(self: _UserRepoDeps, user_id: int, currencies: List[str]):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM user_currencies WHERE user_id=?", (user_id,))
            await conn.executemany("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", [(user_id, c) for c in currencies])
            await conn.commit()
        if user_id in self.user_data:
            self.user_data[user_id]["selected_currencies"] = currencies

    async def get_user_crypto(self: _UserRepoDeps, user_id: int) -> List[str]:
        cached = self.user_data.get(user_id)
        if cached and "selected_crypto" in cached:
            return cached["selected_crypto"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_crypto(self: _UserRepoDeps, user_id: int, crypto_list: List[str]):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM user_crypto WHERE user_id=?", (user_id,))
            await conn.executemany("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", [(user_id, s) for s in crypto_list])
            await conn.commit()
        if user_id in self.user_data:
            self.user_data[user_id]["selected_crypto"] = crypto_list

    async def get_user_language(self: _UserRepoDeps, user_id: int) -> str:
        cached = self.user_data.get(user_id)
        if cached and "language" in cached:
            return cached["language"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] else 'ru'

    async def set_user_language(self: _UserRepoDeps, user_id: int, language: str):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
            await conn.commit()
        if user_id in self.user_data:
            self.user_data[user_id]["language"] = language

    async def get_user_quote_format(self: _UserRepoDeps, user_id: int) -> bool:
        cached = self.user_data.get(user_id)
        if cached and "use_quote_format" in cached:
            return cached["use_quote_format"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT use_quote_format FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return bool(row[0]) if row else True

    async def set_user_quote_format(self: _UserRepoDeps, user_id: int, use_quote: bool):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE users SET use_quote_format=? WHERE user_id=?", (1 if use_quote else 0, user_id))
            await conn.commit()
        if user_id in self.user_data:
            self.user_data[user_id]["use_quote_format"] = use_quote

    async def get_statistics(self: _UserRepoDeps) -> dict:
        today = datetime.now().strftime('%Y-%m-%d')
        conn = await self._get_read_conn()
        async with conn.execute("""
            SELECT 
                (SELECT COUNT(*) FROM users),
                (SELECT COUNT(*) FROM users WHERE last_seen = ?),
                (SELECT COUNT(*) FROM users WHERE first_seen = ?)
        """, (today, today)) as cursor:
            row = await cursor.fetchone()
        return {
            "total_users": row[0] if row else 0,
            "active_today": row[1] if row and row[1] else 0,
            "new_today": row[2] if row and row[2] else 0,
        }

    async def get_all_user_ids(self: _UserRepoDeps) -> List[int]:
        conn = await self._get_read_conn()
        async with conn.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]
