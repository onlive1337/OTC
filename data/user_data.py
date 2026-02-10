import aiosqlite
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
        quote_format INTEGER NOT NULL DEFAULT 0
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
]

class UserData:
    def __init__(self):
        self.user_data: Dict[str, Any] = {}
        self.chat_data: Dict[str, Any] = {}
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')
        self._conn: Optional[aiosqlite.Connection] = None
        self._known_users: Set[int] = set()
        self._known_chats: Set[int] = set()

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
        self._conn = await aiosqlite.connect(DB_PATH)
        self._conn.row_factory = None
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    async def init_db(self):
        conn = await self._get_conn()
        for stmt in INIT_SQL:
            await conn.execute(stmt)
        await conn.commit()
        async with conn.execute("SELECT user_id FROM users") as cursor:
            self._known_users = {row[0] for row in await cursor.fetchall()}
        async with conn.execute("SELECT chat_id FROM chats") as cursor:
            self._known_chats = {row[0] for row in await cursor.fetchall()}
        logger.info(f"DB initialized. Known: {len(self._known_users)} users, {len(self._known_chats)} chats")

    async def close(self):
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None

    async def _ensure_user(self, user_id: int):
        if user_id in self._known_users:
            return
        today = datetime.now().strftime('%Y-%m-%d')
        conn = await self._get_conn()
        async with conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)) as cursor:
            if await cursor.fetchone() is None:
                default_lang = 'ru' if user_id > 0 else 'en'
                await conn.execute(
                    "INSERT INTO users(user_id, interactions, last_seen, first_seen, language, use_quote_format) VALUES(?, 0, ?, ?, ?, 1)",
                    (user_id, today, today, default_lang)
                )
                for cur_code in ACTIVE_CURRENCIES[:5]:
                    await conn.execute("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", (user_id, cur_code))
                for sym in CRYPTO_CURRENCIES[:5]:
                    await conn.execute("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", (user_id, sym))
                await conn.commit()
        self._known_users.add(user_id)

    async def _ensure_chat(self, chat_id: int):
        if chat_id in self._known_chats:
            return
        conn = await self._get_conn()
        async with conn.execute("SELECT chat_id FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            if await cursor.fetchone() is None:
                await conn.execute("INSERT INTO chats(chat_id, quote_format) VALUES(?, 0)", (chat_id,))
                for cur_code in ACTIVE_CURRENCIES[:5]:
                    await conn.execute("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", (chat_id, cur_code))
                for sym in CRYPTO_CURRENCIES[:5]:
                    await conn.execute("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", (chat_id, sym))
                await conn.commit()
        self._known_chats.add(chat_id)
        self.chat_data[str(chat_id)] = True


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


    def initialize_user_data(self, user_id: int):
        today = datetime.now().strftime('%Y-%m-%d')
        default_lang = 'ru' if user_id > 0 else 'en'
        return {
            "interactions": 0,
            "last_seen": today,
            "selected_currencies": ACTIVE_CURRENCIES[:5],
            "selected_crypto": CRYPTO_CURRENCIES[:5],
            "language": default_lang,
            "first_seen": today,
            "use_quote_format": True,
        }

    async def initialize_chat_settings(self, chat_id: int):
        await self._ensure_chat(chat_id)
        logger.info(f"Initialized settings for chat {chat_id}")

    async def update_user_data(self, user_id: int):
        await self._ensure_user(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
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

    async def get_user_crypto(self, user_id: int) -> List[str]:
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

    async def get_user_language(self, user_id: int):
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

    async def get_user_quote_format(self, user_id: int):
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

    async def get_statistics(self):
        today = datetime.now().strftime('%Y-%m-%d')
        conn = await self._get_conn()
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_seen=?", (today,)) as cursor:
            active_today = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM users WHERE first_seen=?", (today,)) as cursor:
            new_today = (await cursor.fetchone())[0]
        return {
            "total_users": total_users,
            "active_today": active_today,
            "new_today": new_today,
        }

    async def get_all_user_ids(self) -> List[int]:
        conn = await self._get_conn()
        async with conn.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]