import asyncio

import aiosqlite
from aiosqlite import OperationalError, IntegrityError
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, DB_PATH

logger = logging.getLogger(__name__)

INIT_SQL = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA cache_size=-64000;",
    "PRAGMA temp_store=MEMORY;",
    "PRAGMA mmap_size=268435456;",
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
    "CREATE INDEX IF NOT EXISTS idx_user_currencies_user ON user_currencies(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_crypto_user ON user_crypto(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_currencies_chat ON chat_currencies(chat_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_crypto_chat ON chat_crypto(chat_id);",
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);",
]

MIGRATIONS = [
    (1, "ALTER TABLE chats ADD COLUMN language TEXT NOT NULL DEFAULT 'ru'"),
]

class UserData:
    MAX_CACHE_SIZE = 5000
    MAX_CHAT_CACHE_SIZE = 1000
    FLUSH_INTERVAL = 30

    def __init__(self):
        self.user_data: Dict[str, Any] = {}
        self.chat_data: Dict[str, Any] = {}
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')
        self._read_conn: Optional[aiosqlite.Connection] = None
        self._write_conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        self._pending_interactions: Dict[int, int] = {}
        self._pending_last_seen: Dict[int, str] = {}
        self._flush_task: Optional[asyncio.Task] = None

    def _cleanup_cache_if_needed(self):
        if len(self.user_data) > self.MAX_CACHE_SIZE:
            sorted_users = sorted(
                self.user_data.items(),
                key=lambda x: x[1].get('last_seen', '1970-01-01') if isinstance(x[1], dict) else '1970-01-01'
            )
            for key, _ in sorted_users[:len(sorted_users) // 2]:
                del self.user_data[key]
            logger.info(f"User cache cleanup: reduced from {len(sorted_users)} to {len(self.user_data)}")

        if len(self.chat_data) > self.MAX_CHAT_CACHE_SIZE:
            items = list(self.chat_data.items())
            for key, _ in items[:len(items) // 2]:
                del self.chat_data[key]
            logger.info(f"Chat cache cleanup: reduced from {len(items)} to {len(self.chat_data)}")

    async def _open_connection(self, readonly: bool = False) -> aiosqlite.Connection:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = await aiosqlite.connect(DB_PATH)
                conn.row_factory = None
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                if readonly:
                    await conn.execute("PRAGMA query_only=ON;")
                    await conn.execute("PRAGMA read_uncommitted=ON;")
                if attempt > 0:
                    logger.info(f"DB {'read' if readonly else 'write'} connection established after {attempt + 1} attempts")
                return conn
            except Exception as e:
                logger.error(f"DB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    raise

    async def _get_read_conn(self) -> aiosqlite.Connection:
        if self._read_conn is not None:
            return self._read_conn
        self._read_conn = await self._open_connection(readonly=True)
        return self._read_conn

    async def _get_write_conn(self) -> aiosqlite.Connection:
        if self._write_conn is not None:
            return self._write_conn
        self._write_conn = await self._open_connection(readonly=False)
        return self._write_conn

    async def _get_conn(self) -> aiosqlite.Connection:
        return await self._get_write_conn()

    async def _get_schema_version(self, conn) -> int:
        try:
            async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else 0
        except OperationalError:
            return 0

    async def init_db(self):
        async with self._write_lock:
            conn = await self._get_write_conn()
            for stmt in INIT_SQL:
                await conn.execute(stmt)

            current_version = await self._get_schema_version(conn)
            for version, sql in MIGRATIONS:
                if version > current_version:
                    try:
                        await conn.execute(sql)
                        await conn.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
                        logger.info(f"Applied migration v{version}")
                    except OperationalError:
                        await conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES(?)", (version,))
                    except Exception as e:
                        logger.error(f"Migration v{version} failed: {e}")

            try:
                await conn.execute("PRAGMA optimize;")
            except Exception:
                pass

            await conn.commit()
            logger.info("DB initialized.")

        await self._get_read_conn()
        self._start_flush_task()

    def _start_flush_task(self):
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush(), name="db_flush_interactions")
            self._flush_task.add_done_callback(
                lambda t: logger.error(f"Flush task failed: {t.exception()}") if not t.cancelled() and t.exception() else None
            )

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            try:
                await self._flush_interactions()
            except asyncio.CancelledError:
                # Final flush before shutdown
                await self._flush_interactions()
                raise
            except Exception:
                logger.exception("Error flushing interactions")

    async def _flush_interactions(self):
        if not self._pending_interactions:
            return

        async with self._write_lock:
            conn = await self._get_write_conn()
            pending = self._pending_interactions.copy()
            last_seen = self._pending_last_seen.copy()
            self._pending_interactions.clear()
            self._pending_last_seen.clear()

            with_seen = [(count, seen, uid) for uid, count in pending.items() if (seen := last_seen.get(uid))]
            without_seen = [(count, uid) for uid, count in pending.items() if uid not in last_seen]

            if with_seen:
                await conn.executemany(
                    "UPDATE users SET interactions = interactions + ?, last_seen=? WHERE user_id=?",
                    with_seen
                )
            if without_seen:
                await conn.executemany(
                    "UPDATE users SET interactions = interactions + ? WHERE user_id=?",
                    without_seen
                )
            await conn.commit()
            logger.debug(f"Flushed {len(pending)} interaction updates")

    async def close(self):
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        try:
            await self._flush_interactions()
        except Exception:
            logger.exception("Error during final interaction flush")

        for conn_name, conn in [("read", self._read_conn), ("write", self._write_conn)]:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    logger.exception(f"Error closing {conn_name} DB connection")
        self._read_conn = None
        self._write_conn = None

    @staticmethod
    def _detect_language(language_code: Optional[str] = None) -> str:
        if not language_code:
            return 'ru'
        cis_codes = ('ru', 'uk', 'be', 'kk', 'uz', 'tg', 'ky')
        return 'ru' if language_code.lower().startswith(cis_codes) else 'en'

    async def _ensure_user(self, user_id: int, language_code: Optional[str] = None):
        if str(user_id) in self.user_data:
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

                self.user_data[str(user_id)] = {
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

    async def _ensure_chat(self, chat_id: int):
        if str(chat_id) in self.chat_data:
            return

        async with self._write_lock:
            conn = await self._get_write_conn()
            async with conn.execute("SELECT chat_id FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
                if await cursor.fetchone() is not None:
                    return
            default_currencies = ACTIVE_CURRENCIES[:5]
            default_crypto = CRYPTO_CURRENCIES[:5]
            try:
                await conn.execute("INSERT INTO chats(chat_id, quote_format, language) VALUES(?, 0, 'ru')", (chat_id,))
                
                currencies_data = [(chat_id, c) for c in default_currencies]
                await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", currencies_data)
                
                crypto_data = [(chat_id, s) for s in default_crypto]
                await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", crypto_data)
                
                await conn.commit()

                self.chat_data[str(chat_id)] = {
                    'currencies': list(default_currencies),
                    'crypto': list(default_crypto),
                    'quote_format': False,
                    'language': 'ru',
                }
            except IntegrityError:
                logger.debug("Chat %s already exists (race condition handled)", chat_id)
            except Exception as e:
                logger.error(f"Error registering chat {chat_id}: {e}")


    async def get_user_data(self, user_id: int):
        self._cleanup_cache_if_needed()

        cached = self.user_data.get(str(user_id))
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
        self.user_data[str(user_id)] = data
        return data

    async def get_chat_data(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'currencies' in cached and 'language' in cached:
            return cached

        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()

        async with conn.execute("""
            SELECT 
                c.quote_format, c.language,
                (SELECT GROUP_CONCAT(currency) FROM chat_currencies WHERE chat_id = c.chat_id) as currencies,
                (SELECT GROUP_CONCAT(symbol) FROM chat_crypto WHERE chat_id = c.chat_id) as crypto
            FROM chats c WHERE c.chat_id = ?
        """, (chat_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return {'currencies': [], 'crypto': [], 'quote_format': False, 'language': 'ru'}

        quote_format, language, currencies_str, crypto_str = row
        currencies = currencies_str.split(',') if currencies_str else []
        crypto = crypto_str.split(',') if crypto_str else []

        data = {
            'currencies': currencies,
            'crypto': crypto,
            'quote_format': bool(quote_format) if quote_format else False,
            'language': language or 'ru',
        }
        self.chat_data[str(chat_id)] = data
        return data


    async def initialize_chat_settings(self, chat_id: int):
        await self._ensure_chat(chat_id)
        logger.info(f"Initialized settings for chat {chat_id}")

    async def update_user_data(self, user_id: int, language_code: Optional[str] = None):
        await self._ensure_user(user_id, language_code=language_code)
        today = datetime.now().strftime('%Y-%m-%d')

        self._cleanup_cache_if_needed()

        user_cache = self.user_data.get(str(user_id))
        is_today = user_cache and user_cache.get("last_seen") == today

        self._pending_interactions[user_id] = self._pending_interactions.get(user_id, 0) + 1
        if not is_today:
            self._pending_last_seen[user_id] = today

        if user_cache:
            user_cache["interactions"] = user_cache.get("interactions", 0) + 1
            if not is_today:
                user_cache["last_seen"] = today
        elif str(user_id) in self.user_data:
            self.user_data[str(user_id)]["interactions"] += 1
            if not is_today:
                self.user_data[str(user_id)]["last_seen"] = today

    def update_chat_cache(self, chat_id: int):
        self.chat_data.pop(str(chat_id), None)
        logger.debug(f"Invalidated chat cache for chat {chat_id}")

    async def get_user_currencies(self, user_id: int):
        cached = self.user_data.get(str(user_id))
        if cached and "selected_currencies" in cached:
            return cached["selected_currencies"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_currencies(self, user_id: int, currencies: List[str]):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
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
        conn = await self._get_read_conn()
        async with conn.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
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
        conn = await self._get_read_conn()
        async with conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] else 'ru'

    async def set_user_language(self, user_id: int, language: str):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
            await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["language"] = language

    async def get_user_quote_format(self, user_id: int):
        cached = self.user_data.get(str(user_id))
        if cached and "use_quote_format" in cached:
            return cached["use_quote_format"]
        await self._ensure_user(user_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT use_quote_format FROM users WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return bool(row[0]) if row else True

    async def set_user_quote_format(self, user_id: int, use_quote: bool):
        await self._ensure_user(user_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE users SET use_quote_format=? WHERE user_id=?", (1 if use_quote else 0, user_id))
            await conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["use_quote_format"] = use_quote

    async def get_chat_quote_format(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'quote_format' in cached:
            return cached['quote_format']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        result = bool(row[0]) if row else False
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['quote_format'] = result
        return result

    async def set_chat_quote_format(self, chat_id: int, use_quote: bool):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE chats SET quote_format=? WHERE chat_id=?", (1 if use_quote else 0, chat_id))
            await conn.commit()
        if str(chat_id) in self.chat_data and isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)]['quote_format'] = use_quote

    async def get_chat_currencies(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'currencies' in cached:
            return cached['currencies']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        currencies = [r[0] for r in rows]
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['currencies'] = currencies
        return currencies

    async def set_chat_currencies(self, chat_id: int, currencies: List[str]):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM chat_currencies WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", [(chat_id, c) for c in currencies])
            await conn.commit()
        if str(chat_id) in self.chat_data and isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)]['currencies'] = currencies

    async def get_chat_crypto(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'crypto' in cached:
            return cached['crypto']
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,)) as cursor:
            rows = await cursor.fetchall()
        crypto = [r[0] for r in rows]
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['crypto'] = crypto
        return crypto

    async def set_chat_crypto(self, chat_id: int, crypto_list: List[str]):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("DELETE FROM chat_crypto WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", [(chat_id, s) for s in crypto_list])
            await conn.commit()
        if str(chat_id) in self.chat_data and isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)]['crypto'] = crypto_list

    async def get_chat_language(self, chat_id: int):
        cached = self.chat_data.get(str(chat_id))
        if isinstance(cached, dict) and 'language' in cached:
            return cached['language']
            
        await self._ensure_chat(chat_id)
        conn = await self._get_read_conn()
        async with conn.execute("SELECT language FROM chats WHERE chat_id=?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        
        lang = row[0] if row and row[0] else 'ru'
        
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['language'] = lang
        
        return lang

    async def set_chat_language(self, chat_id: int, language: str):
        await self._ensure_chat(chat_id)
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("UPDATE chats SET language=? WHERE chat_id=?", (language, chat_id))
            await conn.commit()
        
        if str(chat_id) not in self.chat_data or not isinstance(self.chat_data[str(chat_id)], dict):
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]['language'] = language

    async def get_statistics(self):
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

    async def get_all_user_ids(self) -> List[int]:
        conn = await self._get_read_conn()
        async with conn.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]