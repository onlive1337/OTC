INIT_SQL = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA busy_timeout=5000;",
    "PRAGMA wal_autocheckpoint=1000;",
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
