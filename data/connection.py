import asyncio
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import Dict, Any, Optional

import aiosqlite
from aiosqlite import OperationalError

from config.config import (
    DB_PATH, SQLITE_BUSY_TIMEOUT_MS, SQLITE_WAL_AUTOCHECKPOINT_PAGES,
    DB_BACKUP_INTERVAL_HOURS, DB_BACKUP_KEEP,
)
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
        self._backup_task: Optional[asyncio.Task] = None

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

    @staticmethod
    async def _open_connection(readonly: bool = False) -> aiosqlite.Connection:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = await aiosqlite.connect(DB_PATH)
                conn.row_factory = None
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
                await conn.execute(f"PRAGMA wal_autocheckpoint={SQLITE_WAL_AUTOCHECKPOINT_PAGES};")
                if readonly:
                    await conn.execute("PRAGMA query_only=ON;")
                if attempt > 0:
                    logger.info(f"DB {'read' if readonly else 'write'} connection established after {attempt + 1} attempts")
                return conn
            except sqlite3.Error as e:
                logger.error(f"DB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    raise

        raise RuntimeError("Failed to open database connection after retries")

    async def _get_read_conn(self) -> aiosqlite.Connection:
        if self._read_conn is not None:
            return self._read_conn
        self._read_conn = await self._open_connection(readonly=True)
        conn = self._read_conn
        assert conn is not None
        return conn

    async def _get_write_conn(self) -> aiosqlite.Connection:
        if self._write_conn is not None:
            return self._write_conn
        self._write_conn = await self._open_connection(readonly=False)
        conn = self._write_conn
        assert conn is not None
        return conn

    async def ping_db(self) -> bool:
        try:
            conn = await self._get_read_conn()
            await conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    @staticmethod
    def _backup_dir() -> str:
        return os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), 'backups')

    @classmethod
    def _list_backups(cls) -> list:
        backup_dir = cls._backup_dir()
        try:
            names = os.listdir(backup_dir)
        except FileNotFoundError:
            return []
        return sorted(
            os.path.join(backup_dir, n) for n in names
            if n.startswith('backup-') and n.endswith('.db')
        )

    async def backup_db(self) -> str:
        backup_dir = self._backup_dir()
        os.makedirs(backup_dir, exist_ok=True)
        target = os.path.join(backup_dir, f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db")
        async with self._write_lock:
            conn = await self._get_write_conn()
            await conn.execute("VACUUM INTO ?", (target,))
        self._prune_old_backups()
        logger.info(f"DB backup written to {target}")
        return target

    @classmethod
    def _prune_old_backups(cls):
        if DB_BACKUP_KEEP <= 0:
            return
        backups = cls._list_backups()
        for old in backups[:-DB_BACKUP_KEEP]:
            try:
                os.remove(old)
                logger.info(f"Pruned old DB backup {old}")
            except OSError:
                logger.warning(f"Failed to remove old DB backup {old}")

    def _latest_backup_age(self) -> Optional[float]:
        backups = self._list_backups()
        if not backups:
            return None
        try:
            newest = max(os.path.getmtime(p) for p in backups)
        except OSError:
            return None
        return time.time() - newest

    async def _periodic_backup(self):
        interval = DB_BACKUP_INTERVAL_HOURS * 3600
        while True:
            try:
                age = self._latest_backup_age()
                if age is None or age >= interval:
                    await self.backup_db()
            except asyncio.CancelledError:
                raise
            except (sqlite3.Error, OSError):
                logger.exception("Scheduled DB backup failed")
            await asyncio.sleep(min(interval, 3600))

    @staticmethod
    async def _get_schema_version(conn) -> int:
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
                    except OperationalError as e:
                        if "duplicate column" not in str(e).lower():
                            logger.error(f"Migration v{version} failed: {e}")
                            raise
                        await conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES(?)", (version,))
                    except sqlite3.Error as e:
                        logger.error(f"Migration v{version} failed: {e}")
                        raise

            try:
                await conn.execute("PRAGMA optimize;")
            except sqlite3.Error:
                pass

            await conn.commit()
            logger.info("DB initialized.")

        await self._get_read_conn()
        self._start_flush_task()
        self._start_backup_task()

    def _start_flush_task(self):
        flush_task = self._flush_task
        if flush_task is None or flush_task.done():
            def _on_flush_done(t: asyncio.Task):
                if not t.cancelled() and t.exception():
                    logger.error(f"Flush task failed: {t.exception()}")

            flush_task = asyncio.create_task(self._periodic_flush(), name="db_flush_interactions")
            self._flush_task = flush_task
            flush_task.add_done_callback(_on_flush_done)

    def _start_backup_task(self):
        if DB_BACKUP_INTERVAL_HOURS <= 0:
            return
        backup_task = self._backup_task
        if backup_task is None or backup_task.done():
            def _on_backup_done(t: asyncio.Task):
                if not t.cancelled() and t.exception():
                    logger.error(f"Backup task failed: {t.exception()}")

            backup_task = asyncio.create_task(self._periodic_backup(), name="db_periodic_backup")
            self._backup_task = backup_task
            backup_task.add_done_callback(_on_backup_done)

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            try:
                await self._flush_interactions()
            except asyncio.CancelledError:
                await self._flush_interactions()
                raise
            except sqlite3.Error:
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

            try:
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
            except sqlite3.Error:
                for uid, count in pending.items():
                    self._pending_interactions[uid] = self._pending_interactions.get(uid, 0) + count
                for uid, seen in last_seen.items():
                    self._pending_last_seen.setdefault(uid, seen)
                try:
                    await conn.rollback()
                except sqlite3.Error:
                    logger.warning("Rollback after failed interaction flush also failed")
                raise
            logger.debug(f"Flushed {len(pending)} interaction updates")

    async def close(self):
        for task in (self._flush_task, self._backup_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._flush_task = None
        self._backup_task = None

        try:
            await self._flush_interactions()
        except sqlite3.Error:
            logger.exception("Error during final interaction flush")

        for conn_name, conn in [("read", self._read_conn), ("write", self._write_conn)]:
            if conn is not None:
                try:
                    await conn.close()
                except sqlite3.Error:
                    logger.exception(f"Error closing {conn_name} DB connection")
        self._read_conn = None
        self._write_conn = None
