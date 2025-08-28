import sqlite3
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect('crp_clan.db')
    conn.row_factory = sqlite3.Row
    return conn

def migrate_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(boss_kills)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'is_killed' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN is_killed INTEGER DEFAULT 0")

    if 'respawn_notified' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN respawn_notified INTEGER DEFAULT 0")

    if 'channel_id' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN channel_id INTEGER")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boss_loot'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE boss_loot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boss_kill_id INTEGER,
                user_id INTEGER,
                username TEXT,
                screenshot_path TEXT,
                loot_text TEXT,
                created_at TEXT,
                FOREIGN KEY (boss_kill_id) REFERENCES boss_kills (id)
            )
        ''')

    conn.commit()
    conn.close()

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boss_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_name TEXT,
            kill_time TEXT,
            respawn TEXT,
            message_id INTEGER,
            channel_id INTEGER,
            is_killed INTEGER DEFAULT 0,
            respawn_notified INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boss_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_kill_id INTEGER,
            user_id INTEGER,
            username TEXT,
            attended INTEGER DEFAULT 0,
            FOREIGN KEY (boss_kill_id) REFERENCES boss_kills (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boss_loot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_kill_id INTEGER,
            user_id INTEGER,
            username TEXT,
            screenshot_path TEXT,
            loot_text TEXT,
            created_at TEXT,
            FOREIGN KEY (boss_kill_id) REFERENCES boss_kills (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER UNIQUE,
            username TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')

    conn.commit()
    conn.close()
    migrate_database()