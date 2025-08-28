-- Таблица для веб-пользователей и админских прав
CREATE TABLE IF NOT EXISTS web_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER UNIQUE,
    username TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT
);

-- Таблица для хранения сессий
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    expires_at TEXT,
    FOREIGN KEY (user_id) REFERENCES web_users (id)
);