import web
from datetime import datetime, timedelta
import sqlite3
import json
import logging
import os

from database import init_db, get_db_connection, insert_test_data

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('web_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

urls = (
    '/', 'Index',
    '/bosses', 'Bosses',
    '/loot', 'Loot',
    '/stats', 'Stats',
    '/admin', 'Admin',
    '/login', 'Login',
    '/logout', 'Logout',
    '/api/boss_spawn', 'ApiBossSpawn',
    '/static/(.*)', 'Static',
    '/.*', 'NotFound'
)

app = web.application(urls, globals())


# Функция для определения цвета предмета лута
def get_loot_color_class(loot_text):
    """Определяет CSS класс для цвета предмета на основе его названия"""
    if not loot_text:
        return ''

    loot_lower = loot_text.lower()

    # Зеленый цвет - Homun, Chest
    if any(word in loot_lower for word in ['homun', 'chest']):
        return 'loot-green'

    # Синий цвет - Stone, Part, Fateful, Corrupted, Dark Orh
    elif any(word in loot_lower for word in ['stone', 'part', 'fateful', 'corrupted', 'dark orh']):
        return 'loot-blue'

    # Фиолетовый цвет - Expert, Gray Dawn, Aquleus
    elif any(word in loot_lower for word in ['expert', 'gray dawn', 'aquleus']):
        return 'loot-purple'

    # Оранжевый цвет - Ability
    elif any(word in loot_lower for word in ['ability']):
        return 'loot-orange'

    else:
        return ''


render = web.template.render('templates/', base='base',
                             globals={'str': str, 'get_loot_color_class': get_loot_color_class})

# Конфигурация
web.config.debug = False  # Это важно для работы сессий :cite[1]

# Конфигурация базы данных
DB_PATH = 'crp_clan.db'

# Простая система аутентификации (вместо сложных сессий)
# Будем использовать куки для хранения статуса авторизации
AUTH_COOKIE_NAME = 'crp_clan_admin'


def safe_db_query(query, params=()):
    """Безопасное выполнение запроса к базе данных с обработкой ошибок"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        # Преобразуем Row объекты в словари
        result = [dict(row) for row in result]
        conn.close()
        return result
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return []


def is_authenticated():
    """Проверяет, авторизован ли пользователь"""
    cookie_value = web.cookies().get(AUTH_COOKIE_NAME)
    return cookie_value == 'authenticated'


def set_authenticated(value):
    """Устанавливает статус авторизации"""
    web.setcookie(AUTH_COOKIE_NAME, 'authenticated' if value else '', expires=3600)


class Static:
    def GET(self, path):
        try:
            f = open(f'static/{path}', 'rb')
            return f.read()
        except:
            return 404


class Index:
    def GET(self):
        try:
            # Ближайшие боссы в течение 24 часов
            upcoming_bosses = safe_db_query('''
                SELECT boss_name, respawn 
                FROM boss_kills 
                WHERE datetime(respawn) > datetime('now') 
                AND datetime(respawn) < datetime('now', '+1 day')
                ORDER BY respawn ASC
            ''')

            # Если нет данных, используем тестовые
            if not upcoming_bosses:
                upcoming_bosses = [
                    {'boss_name': 'Venatus - 60 LV', 'respawn': '29.08.25-14:30'},
                    {'boss_name': 'Ego - 70 LV', 'respawn': '29.08.25-18:45'}
                ]

            # Топ боссов по убийствам
            top_bosses = safe_db_query('''
                SELECT boss_name, COUNT(*) as kill_count
                FROM boss_kills 
                WHERE is_killed = 1
                GROUP BY boss_name 
                ORDER BY kill_count DESC 
                LIMIT 10
            ''')

            if not top_bosses:
                top_bosses = [
                    {'boss_name': 'Venatus - 60 LV', 'kill_count': 15},
                    {'boss_name': 'Ego - 70 LV', 'kill_count': 12},
                    {'boss_name': 'Livera - 75 LV', 'kill_count': 8}
                ]

            # Топ игроков за неделю
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%y")
            top_players = safe_db_query('''
                SELECT username, COUNT(*) as attendance_count
                FROM boss_attendance 
                INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id
                WHERE boss_attendance.attended = 1 
                AND boss_kills.kill_time >= ?
                GROUP BY boss_attendance.user_id 
                ORDER BY attendance_count DESC 
                LIMIT 10
            ''', (week_ago,))

            if not top_players:
                top_players = [
                    {'username': 'Player1', 'attendance_count': 10},
                    {'username': 'Player2', 'attendance_count': 8},
                    {'username': 'Player3', 'attendance_count': 7}
                ]

            return render.index(upcoming_bosses, top_bosses, top_players)
        except Exception as e:
            logger.error(f"Ошибка в Index.GET: {e}")
            # Возвращаем шаблон с тестовыми данными при любой ошибке
            upcoming_bosses = [
                {'boss_name': 'Venatus - 60 LV', 'respawn': '29.08.25-14:30'},
                {'boss_name': 'Ego - 70 LV', 'respawn': '29.08.25-18:45'}
            ]
            top_bosses = [
                {'boss_name': 'Venatus - 60 LV', 'kill_count': 15},
                {'boss_name': 'Ego - 70 LV', 'kill_count': 12},
                {'boss_name': 'Livera - 75 LV', 'kill_count': 8}
            ]
            top_players = [
                {'username': 'Player1', 'attendance_count': 10},
                {'username': 'Player2', 'attendance_count': 8},
                {'username': 'Player3', 'attendance_count': 7}
            ]
            return render.index(upcoming_bosses, top_bosses, top_players)


class Loot:
    def GET(self):
        try:
            loot_data = safe_db_query('''
                SELECT bl.*, bk.boss_name, bk.kill_time
                FROM boss_loot bl
                JOIN boss_kills bk ON bl.boss_kill_id = bk.id
                ORDER BY bl.created_at DESC
                LIMIT 50
            ''')

            if not loot_data:
                loot_data = [
                    {
                        'boss_name': 'Venatus - 60 LV',
                        'username': 'Player1',
                        'loot_text': 'Epic Sword, Rare Shield',
                        'created_at': '28.08.25-15:30'
                    },
                    {
                        'boss_name': 'Ego - 70 LV',
                        'username': 'Player2',
                        'loot_text': 'Legendary Armor, Epic Helmet',
                        'created_at': '28.08.25-12:45'
                    }
                ]

            return render.loot(loot_data)
        except Exception as e:
            logger.error(f"Ошибка в Loot.GET: {e}")
            loot_data = [
                {
                    'boss_name': 'Venatus - 60 LV',
                    'username': 'Player1',
                    'loot_text': 'Epic Sword, Rare Shield',
                    'created_at': '28.08.25-15:30'
                },
                {
                    'boss_name': 'Ego - 70 LV',
                    'username': 'Player2',
                    'loot_text': 'Legendary Armor, Epic Helmet',
                    'created_at': '28.08.25-12:45'
                }
            ]
            return render.loot(loot_data)


class Stats:
    def GET(self):
        try:
            time_range = web.input().get('range', 'week')

            # Определяем период для статистики
            if time_range == 'week':
                date_filter = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%y")
            elif time_range == 'last_week':
                date_filter = (datetime.now() - timedelta(days=14)).strftime("%d.%m.%y")
                end_date = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%y")
            elif time_range == 'month':
                date_filter = (datetime.now() - timedelta(days=30)).strftime("%d.%m.%y")
            else:
                date_filter = "01.01.70"

            # Статистика по игрокам
            if time_range == 'last_week':
                player_stats = safe_db_query('''
                    SELECT ba.username, COUNT(*) as attendance_count
                    FROM boss_attendance ba
                    INNER JOIN boss_kills bk ON ba.boss_kill_id = bk.id
                    WHERE ba.attended = 1 
                    AND bk.kill_time >= ? AND bk.kill_time < ?
                    GROUP BY ba.user_id 
                    ORDER BY attendance_count DESC
                ''', (date_filter, end_date))
            else:
                player_stats = safe_db_query('''
                    SELECT ba.username, COUNT(*) as attendance_count
                    FROM boss_attendance ba
                    INNER JOIN boss_kills bk ON ba.boss_kill_id = bk.id
                    WHERE ba.attended = 1 
                    AND bk.kill_time >= ?
                    GROUP BY ba.user_id 
                    ORDER BY attendance_count DESC
                ''', (date_filter,))

            if not player_stats:
                player_stats = [
                    {'username': 'Player1', 'attendance_count': 10},
                    {'username': 'Player2', 'attendance_count': 8},
                    {'username': 'Player3', 'attendance_count': 7}
                ]

            return render.stats(player_stats, time_range)
        except Exception as e:
            logger.error(f"Ошибка в Stats.GET: {e}")
            player_stats = [
                {'username': 'Player1', 'attendance_count': 10},
                {'username': 'Player2', 'attendance_count': 8},
                {'username': 'Player3', 'attendance_count': 7}
            ]
            return render.stats(player_stats, 'week')


class Admin:
    def GET(self):
        # Проверка авторизации
        if not is_authenticated():
            raise web.seeother('/login')

        try:
            bosses = safe_db_query('SELECT DISTINCT boss_name FROM boss_kills ORDER BY boss_name')
            members = safe_db_query('SELECT DISTINCT user_id, username FROM boss_attendance ORDER BY username')

            # Очищаем данные от специальных символов
            for boss in bosses:
                boss['boss_name'] = boss['boss_name'].replace('"', '').replace("'", "") if boss['boss_name'] else ""

            for member in members:
                member['username'] = member['username'].replace('"', '').replace("'", "") if member['username'] else ""

            if not bosses:
                bosses = [{'boss_name': 'Venatus - 60 LV'}, {'boss_name': 'Ego - 70 LV'}]

            if not members:
                members = [
                    {'user_id': 1, 'username': 'Player1'},
                    {'user_id': 2, 'username': 'Player2'}
                ]

            return render.admin(bosses, members)
        except Exception as e:
            logger.error(f"Ошибка в Admin.GET: {e}")
            bosses = [{'boss_name': 'Venatus - 60 LV'}, {'boss_name': 'Ego - 70 LV'}]
            members = [
                {'user_id': 1, 'username': 'Player1'},
                {'user_id': 2, 'username': 'Player2'}
            ]
            return render.admin(bosses, members)


class ApiBossSpawn:
    def POST(self):
        data = web.input()
        boss_name = data.boss_name

        # Здесь будет интеграция с Discord ботом
        return json.dumps({'status': 'success', 'message': f'Босс {boss_name} отмечен как появившийся'})


class Login:
    def GET(self):
        return render.login()

    def POST(self):
        data = web.input()
        # Простая аутентификация (в реальном приложении нужно использовать безопасный метод)
        if data.username == "admin" and data.password == "admin":
            set_authenticated(True)
            raise web.seeother('/admin')
        else:
            return "Неверные учетные данные"


class Logout:
    def GET(self):
        set_authenticated(False)
        raise web.seeother('/')


class NotFound:
    def GET(self):
        path = web.ctx.path
        return render.notfound(path)


if __name__ == "__main__":
    # Инициализируем базу данных
    init_db()

    # Добавляем тестовые данные, если база пустая
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM boss_kills")
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            insert_test_data()
            logger.info("Добавлены тестовые данные в базу")
    except Exception as e:
        logger.error(f"Ошибка при проверке базы данных: {e}")
        insert_test_data()

    app.run()