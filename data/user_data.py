import asyncio

import aiosqlite
from aiosqlite import OperationalError, IntegrityError
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
import logging

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, DB_PATH

logger = logging.getLogger(__name__)

INIT_SQL = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        interactions INTEGER NOT NULL DEFAULT 0,
        last_seen TEXT,
        first_seen TEXT,
        language TEXT NOT NULL DEFAULT 'ru',
        use_quote_format INTEGER NOT NULL DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_currencies (
        user_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        PRIMARY KEY(user_id, currency)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_crypto (
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        PRIMARY KEY(user_id, symbol)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chats (
        chat_id INTEGER PRIMARY KEY,
        quote_format INTEGER NOT NULL DEFAULT 0,
        language TEXT NOT NULL DEFAULT 'ru'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_currencies (
        chat_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        PRIMARY KEY(chat_id, currency)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_crypto (
        chat_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        PRIMARY KEY(chat_id, symbol)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);",
    "CREATE INDEX IF NOT EXISTS idx_users_first_seen ON users(first_seen);",
]

class UserData:
    def __init__(self):
        self.user_data: Dict[str, Any] = {}
        self.chat_data: Dict[str, Any] = {}
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')
        self._conn: Optional[aiosqlite.Connection] = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is not None:
            try:
                await self._conn.execute("SELECT 1")
                return self._conn
            except Exception:
                logger.warning("DB connection lost, reconnecting...")
                try:
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._conn = await aiosqlite.connect(DB_PATH)
                self._conn.row_factory = None
                await self._conn.execute("PRAGMA journal_mode=WAL;")
                await self._conn.execute("PRAGMA synchronous=NORMAL;")
                if attempt > 0:
                    logger.info(f"DB reconnected after {attempt + 1} attempts")
                return self._conn
            except Exception as e:
                logger.error(f"DB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                self._conn = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    raise

    async def init_db(self):
        conn = await self._get_conn()
        for stmt in INIT_SQL:
            await conn.execute(stmt)
        
        try:
            await conn.execute("ALTER TABLE chats ADD COLUMN language TEXT NOT NULL DEFAULT 'ru'")
            logger.info("Migrated chats table: added language column")
        except OperationalError:
            pass
        except Exception as e:
            logger.error(f"Migration error: {e}")

        await conn.commit()
        logger.info("DB initialized.")

    async def close(self):
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None

    @staticmethod
    def _detect_language(language_code: Optional[str] = None) -> str:
        if not language_code:
            return 'ru'
        cis_codes = ('ru', 'uk', 'be', 'kk', 'uz', 'tg', 'ky')
        return 'ru' if language_code.lower().startswith(cis_codes) else 'en'

    async def _ensure_user(self, user_id: int, language_code: Optional[str] = None):
        if str(user_id) in self.user_data:
            return

        conn = await self._get_conn()
        async with conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)) as cursor:
            if await cursor.fetchone() is None:
                default_lang = self._detect_language(language_code)
                try:
                    await conn.execute(
                        "INSERT INTO users(user_id, interactions, last_seen, first_seen, language, use_quote_format) VALUES(?, 0, ?, ?, ?, 1)",
                        (user_id, datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d'), default_lang)
                    )
                    
                    currencies_data = [(user_id, c) for c in ACTIVE_CURRENCIES[:5]]
                    await conn.executemany("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", currencies_data)
                    
                    crypto_data = [(user_id, s) for s in CRYPTO_CURRENCIES[:5]]
                    await conn.executemany("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", crypto_data)
                    
                    await conn.commit()
                    logger.info(f"New user {user_id} registered with language '{default_lang}'")
                except IntegrityError:
                    logger.debug("User %s already exists (race condition handled)", user_id)
                except Exception as e:
                    logger.error(f"Error registering user {user_id}: {e}")

    async def _ensure_chat(self, chat_id: int):
        if str(chat_id) in self.chat_data:
            return
        conn = await self._get_conn()
        async with conn.execute("SELECT chat_id FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            if await cursor.fetchone() is None:
                try:
                    await conn.execute("INSERT INTO chats(chat_id, quote_format, language) VALUES(?, 0, 'ru')", (chat_id,))
                    
                    currencies_data = [(chat_id, c) for c in ACTIVE_CURRENCIES[:5]]
                    await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", currencies_data)
                    
                    crypto_data = [(chat_id, s) for s in CRYPTO_CURRENCIES[:5]]
                    await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", crypto_data)
                    
                    await conn.commit()
                except IntegrityError:
                    logger.debug("Chat %s already exists (race condition handled)", chat_id)
                except Exception as e:
                    logger.error(f"Error registering chat {chat_id}: {e}")


    async def get_user_data(self, user_id: int):
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT interactions, last_seen, first_seen, language, use_quote_format FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            interactions, last_seen, first_seen, language, use_quote = row

        async with conn.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,)) as cursor:
            currencies = [r[0] for r in await cursor.fetchall()]

        async with conn.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,)) as cursor:
            crypto = [r[0] for r in await cursor.fetchall()]

        data = {
            "interactions": interactions,
            "last_seen": last_seen,
            "selected_currencies": currencies,
            "selected_crypto": crypto,
            "language": language or 'ru',
            "first_seen": first_seen,
            "use_quote_format": bool(use_quote),
        }
        self.user_data[str(user_id)] = data
        return data

    async def get_chat_data(self, chat_id: int):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            quote_format = bool(row[0]) if row else False
        
        async with conn.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,)) as cursor:
            currencies = [r[0] for r in await cursor.fetchall()]
        
        async with conn.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,)) as cursor:
            crypto = [r[0] for r in await cursor.fetchall()]

        data = {
            'currencies': currencies,
            'crypto': crypto,
            'quote_format': quote_format,
        }
        self.chat_data[str(chat_id)] = data
        return data


    async def initialize_chat_settings(self, chat_id: int):
        await self._ensure_chat(chat_id)
        logger.info(f"Initialized settings for chat {chat_id}")

    async def update_user_data(self, user_id: int, language_code: Optional[str] = None):
        await self._ensure_user(user_id, language_code=language_code)
        today = datetime.now().strftime('%Y-%m-%d')
        
        user_cache = self.user_data.get(str(user_id))
        is_today = user_cache and user_cache.get("last_seen") == today
        
        if is_today:
            if user_cache:
                user_cache["interactions"] += 1
            return
            
        conn = await self._get_conn()
        await conn.execute("UPDATE users SET interactions = interactions + 1, last_seen=? WHERE user_id=?", (today, user_id))
        await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["interactions"] += 1
            self.user_data[str(user_id)]["last_seen"] = today

    def update_chat_cache(self, chat_id: int):
        self.chat_data[str(chat_id)] = True
        logger.info(f"Updated chat cache for chat {chat_id}")

    async def get_user_currencies(self, user_id: int):
        cached = self.user_data.get(str(user_id))
        if cached and "selected_currencies" in cached:
            return cached["selected_currencies"]
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_currencies(self, user_id: int, currencies: List[str]):
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        await conn.execute("DELETE FROM user_currencies WHERE user_id=?", (user_id,))
        await conn.executemany("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", [(user_id, c) for c in currencies])
        await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["selected_currencies"] = currencies

    async def get_user_crypto(self, user_id: int) -> List[str]:
        cached = self.user_data.get(str(user_id))
        if cached and "selected_crypto" in cached:
            return cached["selected_crypto"]
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        await conn.execute("DELETE FROM user_crypto WHERE user_id=?", (user_id,))
        await conn.executemany("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", [(user_id, s) for s in crypto_list])
        await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["selected_crypto"] = crypto_list

    async def get_user_language(self, user_id: int):
        cached = self.user_data.get(str(user_id))
        if cached and "language" in cached:
            return cached["language"]
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] else 'ru'

    async def set_user_language(self, user_id: int, language: str):
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        await conn.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
        await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["language"] = language

    async def get_user_quote_format(self, user_id: int):
        cached = self.user_data.get(str(user_id))
        if cached and "use_quote_format" in cached:
            return cached["use_quote_format"]
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT use_quote_format FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return bool(row[0]) if row else True

    async def set_user_quote_format(self, user_id: int, use_quote: bool):
        await self._ensure_user(user_id)
        conn = await self._get_conn()
        await conn.execute("UPDATE users SET use_quote_format=? WHERE user_id=?", (1 if use_quote else 0, user_id))
        await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["use_quote_format"] = use_quote

    async def get_chat_quote_format(self, chat_id: int):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        return bool(row[0]) if row else False

    async def set_chat_quote_format(self, chat_id: int, use_quote: bool):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        await conn.execute("UPDATE chats SET quote_format=? WHERE chat_id=?", (1 if use_quote else 0, chat_id))
        await conn.commit()

    async def get_chat_currencies(self, chat_id: int):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_chat_currencies(self, chat_id: int, currencies: List[str]):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        await conn.execute("DELETE FROM chat_currencies WHERE chat_id=?", (chat_id,))
        await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", [(chat_id, c) for c in currencies])
        await conn.commit()

    async def get_chat_crypto(self, chat_id: int):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_chat_crypto(self, chat_id: int, crypto_list: List[str]):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        await conn.execute("DELETE FROM chat_crypto WHERE chat_id=?", (chat_id,))
        await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", [(chat_id, s) for s in crypto_list])
        await conn.commit()

    async def get_chat_language(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'language' in cached:
            return cached['language']
            
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        async with conn.execute("SELECT language FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        
        lang = row[0] if row and row[0] else 'ru'
        
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['language'] = lang
        
        return lang

    async def set_chat_language(self, chat_id: int, language: str):
        await self._ensure_chat(chat_id)
        conn = await self._get_conn()
        await conn.execute("UPDATE chats SET language=? WHERE chat_id=?", (language, chat_id))
        await conn.commit()
        
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['language'] = language

    async def get_statistics(self):
        today = datetime.now().strftime('%Y-%m-%d')
        conn = await self._get_conn()
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

    async def get_all_user_ids(self) -> List[int]:
        conn = await self._get_conn()
        async with conn.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]