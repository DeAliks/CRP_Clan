import sqlite3
import logging

logger = logging.getLogger(__name__)

# В конце database.py добавьте
def insert_test_data():
    """Добавляет тестовые данные в базу"""
    # ... (код функции выше)

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


def insert_test_data():
    """Добавляет тестовые данные в базу"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Добавляем тестовых боссов
        from datetime import datetime, timedelta
        now = datetime.now()

        test_bosses = [
            ('Venatus - 60 LV', (now - timedelta(hours=2)).strftime("%d.%m.%y-%H:%M"),
             (now + timedelta(hours=8)).strftime("%d.%m.%y-%H:%M"), 1, 0, 123456789),
            ('Ego - 70 LV', (now - timedelta(days=1)).strftime("%d.%m.%y-%H:%M"),
             (now + timedelta(hours=20)).strftime("%d.%m.%y-%H:%M"), 1, 0, 123456790),
            ('Livera - 75 LV', (now - timedelta(days=2)).strftime("%d.%m.%y-%H:%M"),
             (now + timedelta(hours=22)).strftime("%d.%m.%y-%H:%M"), 1, 0, 123456791)
        ]

        cursor.executemany(
            'INSERT INTO boss_kills (boss_name, kill_time, respawn, is_killed, respawn_notified, message_id) VALUES (?, ?, ?, ?, ?, ?)',
            test_bosses
        )

        # Получаем ID добавленных боссов
        cursor.execute("SELECT id FROM boss_kills")
        boss_ids = [row[0] for row in cursor.fetchall()]

        # Добавляем тестовых участников
        test_attendance = []
        for boss_id in boss_ids:
            test_attendance.extend([
                (boss_id, 1, 'Player1', 1),
                (boss_id, 2, 'Player2', 1),
                (boss_id, 3, 'Player3', 1)
            ])

        cursor.executemany(
            'INSERT INTO boss_attendance (boss_kill_id, user_id, username, attended) VALUES (?, ?, ?, ?)',
            test_attendance
        )

        # Добавляем тестовый дроп
        test_loot = [
            (boss_ids[0], 1, 'Player1', '/path/to/screenshot1.png', 'Epic Sword, Rare Shield',
             now.strftime("%d.%m.%y-%H:%M")),
            (boss_ids[1], 2, 'Player2', '/path/to/screenshot2.png', 'Legendary Armor, Epic Helmet',
             (now - timedelta(hours=5)).strftime("%d.%m.%y-%H:%M"))
        ]

        cursor.executemany(
            'INSERT INTO boss_loot (boss_kill_id, user_id, username, screenshot_path, loot_text, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            test_loot
        )

        conn.commit()
        logger.info("Тестовые данные успешно добавлены в базу")
    except Exception as e:
        logger.error(f"Ошибка при добавлении тестовых данных: {e}")
        conn.rollback()
    finally:
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