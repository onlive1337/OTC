import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import aiosqlite
from aiosqlite import OperationalError

from config.config import DB_PATH
from data.schema import INIT_SQL, MIGRATIONS

logger = logging.getLogger(__name__)


class DatabaseMixin:
    MAX_CACHE_SIZE = 5000
    MAX_CHAT_CACHE_SIZE = 1000
    FLUSH_INTERVAL = 30

    def __init__(self):
        self.user_data: Dict[int, Any] = {}
        self.chat_data: Dict[int, Any] = {}
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
