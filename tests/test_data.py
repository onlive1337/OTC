import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import data.connection as connection
from data.user_data import UserData


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(connection, "DB_PATH", path)
    return path


class TestUserRepo:
    def test_register_defaults(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                data = await db.get_user_data(123)
                assert data["language"] == "ru"  # no language_code -> ru
                assert data["use_quote_format"] is True
                assert len(data["selected_currencies"]) == 5
                assert len(data["selected_crypto"]) == 5
            finally:
                await db.close()

        _run(scenario())

    def test_language_detection_en(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.update_user_data(1, language_code="en-US")
                assert await db.get_user_language(1) == "en"
                await db.update_user_data(2, language_code="uk")
                assert await db.get_user_language(2) == "ru"  # CIS -> ru
            finally:
                await db.close()

        _run(scenario())

    def test_set_get_currencies_and_crypto(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.set_user_currencies(42, ["USD", "EUR"])
                assert await db.get_user_currencies(42) == ["USD", "EUR"]
                await db.set_user_crypto(42, ["BTC", "TON"])
                assert await db.get_user_crypto(42) == ["BTC", "TON"]
            finally:
                await db.close()

        _run(scenario())

    def test_quote_format_toggle(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.set_user_quote_format(7, False)
                assert await db.get_user_quote_format(7) is False
                await db.set_user_quote_format(7, True)
                assert await db.get_user_quote_format(7) is True
                await db.set_user_rich_format(7, True)
                assert await db.get_user_rich_format(7) is True
                assert await db.get_user_quote_format(7) is False
                await db.set_user_rich_format(7, False)
                assert await db.get_user_rich_format(7) is False
            finally:
                await db.close()

        _run(scenario())

    def test_display_format_mutual_exclusivity_and_legacy_normalization(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                assert await db.get_user_display_format(7) == "quote"
                await db.set_user_display_format(7, "plain")
                assert await db.get_user_display_format(7) == "plain"
                assert await db.get_user_quote_format(7) is False
                assert await db.get_user_rich_format(7) is False

                await db.set_user_display_format(7, "table")
                assert await db.get_user_display_format(7) == "table"
                assert await db.get_user_quote_format(7) is False
                assert await db.get_user_rich_format(7) is True

                await db.set_user_quote_format(7, True)
                assert await db.get_user_display_format(7) == "quote"
                assert await db.get_user_rich_format(7) is False

                assert await db.get_chat_display_format(-100) == "plain"
                await db.set_chat_display_format(-100, "quote")
                assert await db.get_chat_display_format(-100) == "quote"
                assert await db.get_chat_rich_format(-100) is False
                await db.set_chat_display_format(-100, "table")
                assert await db.get_chat_display_format(-100) == "table"
                assert await db.get_chat_quote_format(-100) is False

                # Simulate legacy DB row where both flags were 1
                conn = await db._get_write_conn()
                await conn.execute(
                    "UPDATE users SET use_quote_format=1, use_rich_format=1 WHERE user_id=7"
                )
                await conn.execute(
                    "UPDATE chats SET quote_format=1, rich_format=1 WHERE chat_id=-100"
                )
                await conn.commit()
                db.user_data.pop(7, None)
                db.chat_data.pop(-100, None)
                assert await db.get_user_display_format(7) == "table"
                assert await db.get_chat_display_format(-100) == "table"
            finally:
                await db.close()

        _run(scenario())

    def test_statistics_counts(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.get_user_data(1)
                await db.get_user_data(2)
                await db.get_user_data(3)
                stats = await db.get_statistics()
                assert stats["total_users"] == 3
                assert stats["new_today"] == 3
                assert stats["active_today"] == 3
            finally:
                await db.close()

        _run(scenario())

    def test_interactions_flush(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.get_user_data(99)  # register
                await db.update_user_data(99)
                await db.update_user_data(99)
                await db._flush_interactions()
                conn = await db._get_read_conn()
                async with conn.execute(
                    "SELECT interactions FROM users WHERE user_id=?", (99,)
                ) as cur:
                    row = await cur.fetchone()
                assert row[0] == 2
            finally:
                await db.close()

        _run(scenario())

    def test_get_all_user_ids(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.get_user_data(10)
                await db.get_user_data(20)
                ids = await db.get_all_user_ids()
                assert set(ids) == {10, 20}
            finally:
                await db.close()

        _run(scenario())


class TestChatRepo:
    def test_chat_defaults_and_set(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                data = await db.get_chat_data(-100)
                assert data["language"] == "en"  # chats default to en
                assert len(data["currencies"]) == 5
                await db.set_chat_currencies(-100, ["USD", "JPY"])
                assert sorted(await db.get_chat_currencies(-100)) == ["JPY", "USD"]
                await db.set_chat_language(-100, "ru")
                assert await db.get_chat_language(-100) == "ru"
                assert await db.get_chat_rich_format(-100) is False
                await db.set_chat_rich_format(-100, True)
                assert await db.get_chat_rich_format(-100) is True
            finally:
                await db.close()

        _run(scenario())

    def test_migrations_v2_v3_upgrade_legacy_schema(self, db_path):
        legacy = sqlite3.connect(db_path)
        try:
            legacy.executescript(
                """
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    interactions INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT,
                    first_seen TEXT,
                    language TEXT NOT NULL DEFAULT 'ru',
                    use_quote_format INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE chats (
                    chat_id INTEGER PRIMARY KEY,
                    quote_format INTEGER NOT NULL DEFAULT 0,
                    language TEXT NOT NULL DEFAULT 'ru'
                );
                CREATE TABLE schema_version (version INTEGER NOT NULL);
                INSERT INTO schema_version(version) VALUES (1);
                INSERT INTO users(user_id, language, use_quote_format) VALUES (5, 'en', 1);
                INSERT INTO chats(chat_id, quote_format, language) VALUES (-55, 0, 'ru');
                """
            )
            legacy.commit()
        finally:
            legacy.close()

        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                u = await db.get_user_data(5)
                c = await db.get_chat_data(-55)
                assert u["use_rich_format"] is False
                assert c["rich_format"] is False
                await db.set_user_rich_format(5, True)
                await db.set_chat_rich_format(-55, True)
                assert await db.get_user_rich_format(5) is True
                assert await db.get_chat_rich_format(-55) is True
            finally:
                await db.close()

        _run(scenario())


class TestBackups:
    def test_backup_db_creates_valid_copy(self, db_path, monkeypatch):
        monkeypatch.setattr(connection, "DB_BACKUP_INTERVAL_HOURS", 0)

        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.set_user_language(777, "en")
                return await db.backup_db()
            finally:
                await db.close()

        target = _run(scenario())
        assert os.path.exists(target)

        backup_conn = sqlite3.connect(target)
        try:
            row = backup_conn.execute("SELECT language FROM users WHERE user_id=777").fetchone()
        finally:
            backup_conn.close()
        assert row == ("en",)

    def test_backup_pruning_keeps_newest(self, db_path, monkeypatch):
        monkeypatch.setattr(connection, "DB_BACKUP_INTERVAL_HOURS", 0)
        monkeypatch.setattr(connection, "DB_BACKUP_KEEP", 2)

        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                return [await db.backup_db() for _ in range(3)]
            finally:
                await db.close()

        made = _run(scenario())
        assert connection.DatabaseMixin._list_backups() == sorted(made)[-2:]

    def test_periodic_backup_runs_on_startup_when_none_exists(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                for _ in range(50):
                    if connection.DatabaseMixin._list_backups():
                        break
                    await asyncio.sleep(0.05)
            finally:
                await db.close()

        _run(scenario())
        assert len(connection.DatabaseMixin._list_backups()) == 1


class TestFlushFailureRecovery:
    def test_failed_flush_restores_pending(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            try:
                await db.get_user_data(99)
                await db.update_user_data(99)
                await db.update_user_data(99)

                # force the write to fail once
                conn = await db._get_write_conn()
                original = conn.executemany

                async def boom(*args, **kwargs):
                    raise sqlite3.OperationalError("disk I/O error")

                conn.executemany = boom
                with pytest.raises(sqlite3.OperationalError):
                    await db._flush_interactions()
                conn.executemany = original

                # counters must survive the failure and flush on retry
                assert db._pending_interactions.get(99) == 2
                await db._flush_interactions()
                read_conn = await db._get_read_conn()
                async with read_conn.execute(
                    "SELECT interactions FROM users WHERE user_id=?", (99,)
                ) as cur:
                    row = await cur.fetchone()
                assert row[0] == 2
            finally:
                await db.close()

        _run(scenario())


class TestPersistenceAcrossRestart:
    def test_data_survives_reopen(self, db_path):
        async def scenario():
            db1 = UserData()
            await db1.init_db()
            await db1.set_user_currencies(777, ["GBP"])
            await db1.set_user_language(777, "en")
            await db1.close()

            # Re-open the same DB file (same loop) to simulate a restart.
            db2 = UserData()
            await db2.init_db()
            try:
                assert await db2.get_user_currencies(777) == ["GBP"]
                assert await db2.get_user_language(777) == "en"
            finally:
                await db2.close()

        _run(scenario())


class TestCacheLRU:
    def test_user_cache_lru_eviction(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            db.MAX_CACHE_SIZE = 2
            try:
                await db.get_user_data(1)
                await db.get_user_data(2)
                assert list(db.user_data.keys()) == [1, 2]

                # Reading user 1 moves it to MRU so user 2 gets evicted next.
                assert await db.get_user_language(1) == "ru"
                assert list(db.user_data.keys()) == [2, 1]

                await db.get_user_data(3)
                assert list(db.user_data.keys()) == [1, 3]
                assert 2 not in db.user_data
            finally:
                await db.close()

        _run(scenario())

    def test_chat_cache_lru_eviction(self, db_path):
        async def scenario():
            db = UserData()
            await db.init_db()
            db.MAX_CHAT_CACHE_SIZE = 2
            try:
                await db.get_chat_data(-10)
                await db.get_chat_data(-20)
                assert list(db.chat_data.keys()) == [-10, -20]

                assert await db.get_chat_language(-10) == "en"
                assert list(db.chat_data.keys()) == [-20, -10]

                await db.get_chat_data(-30)
                assert list(db.chat_data.keys()) == [-10, -30]
                assert -20 not in db.chat_data
            finally:
                await db.close()

        _run(scenario())
