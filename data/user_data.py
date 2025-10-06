import sqlite3
from datetime import datetime
from typing import List, Dict, Any
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
        self._init_db()
        self.user_data: Dict[str, Any] = {}
        self.chat_data: Dict[str, Any] = {}
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        with self._connect() as conn:
            cur = conn.cursor()
            for stmt in INIT_SQL:
                cur.execute(stmt)
            conn.commit()

    def _ensure_user(self, user_id: int):
        today = datetime.now().strftime('%Y-%m-%d')
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
            if cur.fetchone() is None:
                default_lang = 'ru' if user_id > 0 else 'en'
                cur.execute(
                    "INSERT INTO users(user_id, interactions, last_seen, first_seen, language, use_quote_format) VALUES(?, 0, ?, ?, ?, 1)",
                    (user_id, today, today, default_lang)
                )
                for cur_code in ACTIVE_CURRENCIES[:5]:
                    cur.execute("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", (user_id, cur_code))
                for sym in CRYPTO_CURRENCIES[:5]:
                    cur.execute("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", (user_id, sym))
                conn.commit()

    def _ensure_chat(self, chat_id: int):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT chat_id FROM chats WHERE chat_id=?", (chat_id,))
            if cur.fetchone() is None:
                cur.execute("INSERT INTO chats(chat_id, quote_format) VALUES(?, 0)", (chat_id,))
                for cur_code in ACTIVE_CURRENCIES[:5]:
                    cur.execute("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", (chat_id, cur_code))
                for sym in CRYPTO_CURRENCIES[:5]:
                    cur.execute("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", (chat_id, sym))
                conn.commit()
            self.chat_data[str(chat_id)] = True


    def get_user_data(self, user_id: int):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT interactions, last_seen, first_seen, language, use_quote_format FROM users WHERE user_id=?", (user_id,))
            row = cur.fetchone()
            interactions, last_seen, first_seen, language, use_quote = row
            cur.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,))
            currencies = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,))
            crypto = [r[0] for r in cur.fetchall()]
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

    def get_chat_data(self, chat_id: int):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
            quote_format = bool(row[0]) if row else False
            cur.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,))
            currencies = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,))
            crypto = [r[0] for r in cur.fetchall()]
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

    def initialize_chat_settings(self, chat_id: int):
        self._ensure_chat(chat_id)
        logger.info(f"Initialized settings for chat {chat_id}")

    def update_user_data(self, user_id: int):
        self._ensure_user(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET interactions = interactions + 1, last_seen=? WHERE user_id=?", (today, user_id))
            conn.commit()
        if str(user_id) in self.user_data:
            self.user_data[str(user_id)]["interactions"] += 1
            self.user_data[str(user_id)]["last_seen"] = today

    def update_chat_cache(self, chat_id: int):
        self.chat_data[str(chat_id)] = True
        logger.info(f"Updated chat cache for chat {chat_id}")

    def get_user_currencies(self, user_id: int):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT currency FROM user_currencies WHERE user_id=?", (user_id,))
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def set_user_currencies(self, user_id: int, currencies: List[str]):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_currencies WHERE user_id=?", (user_id,))
            cur.executemany("INSERT OR IGNORE INTO user_currencies(user_id, currency) VALUES(?, ?)", [(user_id, c) for c in currencies])
            conn.commit()

    def get_user_crypto(self, user_id: int) -> List[str]:
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT symbol FROM user_crypto WHERE user_id=?", (user_id,))
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_crypto WHERE user_id=?", (user_id,))
            cur.executemany("INSERT OR IGNORE INTO user_crypto(user_id, symbol) VALUES(?, ?)", [(user_id, s) for s in crypto_list])
            conn.commit()

    def get_user_language(self, user_id: int):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
            row = cur.fetchone()
        return row[0] if row and row[0] else 'ru'

    def set_user_language(self, user_id: int, language: str):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
            conn.commit()

    def get_user_quote_format(self, user_id: int):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT use_quote_format FROM users WHERE user_id=?", (user_id,))
            row = cur.fetchone()
        return bool(row[0]) if row else True

    def set_user_quote_format(self, user_id: int, use_quote: bool):
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET use_quote_format=? WHERE user_id=?", (1 if use_quote else 0, user_id))
            conn.commit()

    def get_chat_quote_format(self, chat_id: int):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT quote_format FROM chats WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
        return bool(row[0]) if row else False

    def set_chat_quote_format(self, chat_id: int, use_quote: bool):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE chats SET quote_format=? WHERE chat_id=?", (1 if use_quote else 0, chat_id))
            conn.commit()

    def get_chat_currencies(self, chat_id: int):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT currency FROM chat_currencies WHERE chat_id=?", (chat_id,))
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def set_chat_currencies(self, chat_id: int, currencies: List[str]):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM chat_currencies WHERE chat_id=?", (chat_id,))
            cur.executemany("INSERT OR IGNORE INTO chat_currencies(chat_id, currency) VALUES(?, ?)", [(chat_id, c) for c in currencies])
            conn.commit()

    def get_chat_crypto(self, chat_id: int):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT symbol FROM chat_crypto WHERE chat_id=?", (chat_id,))
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def set_chat_crypto(self, chat_id: int, crypto_list: List[str]):
        self._ensure_chat(chat_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM chat_crypto WHERE chat_id=?", (chat_id,))
            cur.executemany("INSERT OR IGNORE INTO chat_crypto(chat_id, symbol) VALUES(?, ?)", [(chat_id, s) for s in crypto_list])
            conn.commit()

    def get_statistics(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE last_seen=?", (today,))
            active_today = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE first_seen=?", (today,))
            new_today = cur.fetchone()[0]
        return {
            "total_users": total_users,
            "active_today": active_today,
            "new_today": new_today,
        }