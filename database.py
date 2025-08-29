import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_db_connection():
    conn = sqlite3.connect('crp_clan.db')
    conn.row_factory = sqlite3.Row
    return conn


def migrate_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Миграция формата дат
    # ИСПРАВЛЕНИЕ: Убрали попытку выбрать created_at из boss_kills
    cursor.execute("SELECT id, kill_time, respawn FROM boss_kills")  # Убрали created_at
    boss_kills = cursor.fetchall()

    for boss in boss_kills:
        try:
            # Преобразуем старый формат дат в новый ISO формат
            if boss['kill_time'] and '.' in boss['kill_time'] and '-' in boss['kill_time']:
                day, month, year_time = boss['kill_time'].split('.')
                year, time = year_time.split('-')
                new_kill_time = f"20{year}-{month}-{day} {time}:00"

                cursor.execute("UPDATE boss_kills SET kill_time = ? WHERE id = ?",
                               (new_kill_time, boss['id']))
        except:
            pass

        try:
            if boss['respawn'] and '.' in boss['respawn'] and '-' in boss['respawn']:
                day, month, year_time = boss['respawn'].split('.')
                year, time = year_time.split('-')
                new_respawn = f"20{year}-{month}-{day} {time}:00"

                cursor.execute("UPDATE boss_kills SET respawn = ? WHERE id = ?",
                               (new_respawn, boss['id']))
        except:
            pass

    # ИСПРАВЛЕНИЕ: Теперь выбираем created_at только из boss_loot
    cursor.execute("SELECT id, created_at FROM boss_loot")
    loots = cursor.fetchall()

    for loot in loots:
        try:
            if loot['created_at'] and '.' in loot['created_at'] and '-' in loot['created_at']:
                day, month, year_time = loot['created_at'].split('.')
                year, time = year_time.split('-')
                new_created_at = f"20{year}-{month}-{day} {time}:00"

                cursor.execute("UPDATE boss_loot SET created_at = ? WHERE id = ?",
                               (new_created_at, loot['id']))
        except:
            pass

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


def insert_test_data():
    """Добавляет тестовые данные в базу"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Добавляем тестовых боссов
        now = datetime.now()

        test_bosses = [
            ('Venatus - 60 LV', (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
             (now + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"), 1, 0, 123456789),
            ('Ego - 70 LV', (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
             (now + timedelta(hours=20)).strftime("%Y-%m-%d %H:%M"), 1, 0, 123456790),
            ('Livera - 75 LV', (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
             (now + timedelta(hours=22)).strftime("%Y-%m-%d %H:%M"), 1, 0, 123456791)
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
             now.strftime("%Y-%m-%d %H:%M")),
            (boss_ids[1], 2, 'Player2', '/path/to/screenshot2.png', 'Legendary Armor, Epic Helmet',
             (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"))
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