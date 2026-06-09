import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import data.connection as connection
from data.user_data import UserData


def _run(coro):
    """Run a coroutine on a fresh event loop.

    Each test must do all of its DB work inside a single _run() call: the
    aiosqlite connections opened by UserData are bound to the loop that created
    them, so they cannot be reused across separate asyncio.run() invocations.
    """
    return asyncio.run(coro)


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    path = str(tmp_path / "test.db")
    # connection.py binds DB_PATH at import time; point it at a temp file.
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
