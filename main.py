import discord
from discord.ext import commands
import sqlite3
import datetime
import os
from dotenv import load_dotenv
import asyncio

# Загрузка переменных окружения
load_dotenv()

# Проверка наличия токена
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("ОШИБКА: Токен не найден!")
    print("Создайте файл .env с содержимым: DISCORD_TOKEN=ваш_токен")
    exit(1)

# Проверяем формат токена
if not TOKEN.startswith('MT') or len(TOKEN) < 50:
    print("ОШИБКА: Неверный формат токена!")
    print("Проверьте токен в Discord Developer Portal")
    exit(1)

intents = discord.Intents.default()
intents.reactions = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Словарь с боссами и их респауном (в часах)
BOSS_RESPAWNS = {
    "Venatus - 60 LV": 10,
    "Viorent - 65 LV": 10,
    "Ego - 70 LV": 21,
    "Livera - 75 LV": 24,
    "Araneo - 75 LV": 24,
    "Undomiel - 80 LV": 24,
    "Lady Dalia 85 LV": 18,
    "Amentis - 88 LV": 29,
    "Baron - 88 LV": 32,
    "Wannitas - 93 LV": 48,
    "Metus - 93 LV": 48,
}

# Подключение к БД
def get_db_connection():
    return sqlite3.connect('crp_clan.db')

# Инициализация таблиц
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boss_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_name TEXT,
            kill_time TEXT,
            respawn TEXT,
            message_id INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boss_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_kill_id INTEGER,
            user_id INTEGER,
            username TEXT,
            attended INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно подключился!')
    init_db()
    print('База данных инициализирована')

@bot.command()
async def spawn_boss(ctx, *, boss_name):
    if ctx.channel.name != "boss_alert":
        return

    if boss_name not in BOSS_RESPAWNS:
        await ctx.send("Неизвестный босс!")
        return

    try:
        message = await ctx.send(
            f"@everyone\nбосс - {boss_name} - сейчас появится\n"
            "для отметки участия на боссе поставьте реакцию"
        )
        await message.add_reaction("✅")

        now = datetime.datetime.now()
        kill_time = (now + datetime.timedelta(minutes=5)).strftime("%d.%m.%y-%H:%M")
        respawn_hours = BOSS_RESPAWNS[boss_name]
        respawn_time = (now + datetime.timedelta(hours=respawn_hours)).strftime("%d.%m.%y-%H:%M")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO boss_kills (boss_name, kill_time, respawn, message_id) VALUES (?, ?, ?, ?)',
            (boss_name, kill_time, respawn_time, message.id)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"Ошибка в команде spawn_boss: {e}")
        await ctx.send("Произошла ошибка при создании уведомления о боссе")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT id FROM boss_kills WHERE message_id = ?',
                (reaction.message.id,)
            )
            boss_kill = cursor.fetchone()

            if boss_kill:
                cursor.execute(
                    'SELECT * FROM boss_attendance WHERE boss_kill_id = ? AND user_id = ?',
                    (boss_kill[0], user.id)
                )
                existing = cursor.fetchone()

                if not existing:
                    cursor.execute(
                        'INSERT INTO boss_attendance (boss_kill_id, user_id, username, attended) VALUES (?, ?, ?, 1)',
                        (boss_kill[0], user.id, str(user))
                    )
                else:
                    cursor.execute(
                        'UPDATE boss_attendance SET attended = 1 WHERE boss_kill_id = ? AND user_id = ?',
                        (boss_kill[0], user.id)
                    )

                conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка при добавлении реакции: {e}")

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT id FROM boss_kills WHERE message_id = ?',
                (reaction.message.id,)
            )
            boss_kill = cursor.fetchone()

            if boss_kill:
                cursor.execute(
                    'UPDATE boss_attendance SET attended = 0 WHERE boss_kill_id = ? AND user_id = ?',
                    (boss_kill[0], user.id)
                )
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка при удалении реакции: {e}")

@bot.command()
async def boss_rate(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        today = datetime.datetime.now().strftime("%d.%m.%y")
        cursor.execute('SELECT COUNT(*) FROM boss_kills WHERE kill_time LIKE ?', (f'{today}%',))
        total_bosses_today = cursor.fetchone()[0] or 0

        cursor.execute(
            '''SELECT COUNT(*) FROM boss_attendance 
               INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
               WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1 
               AND boss_kills.kill_time LIKE ?''',
            (member.id, f'{today}%')
        )
        attended_today = cursor.fetchone()[0] or 0

        week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%d.%m.%y")
        cursor.execute('SELECT COUNT(*) FROM boss_kills WHERE kill_time >= ?', (week_ago,))
        total_bosses_week = cursor.fetchone()[0] or 0

        cursor.execute(
            '''SELECT COUNT(*) FROM boss_attendance 
               INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
               WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1 
               AND boss_kills.kill_time >= ?''',
            (member.id, week_ago)
        )
        attended_week = cursor.fetchone()[0] or 0

        cursor.execute('SELECT COUNT(*) FROM boss_kills')
        total_bosses = cursor.fetchone()[0] or 0

        cursor.execute(
            '''SELECT COUNT(*) FROM boss_attendance 
               INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
               WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1''',
            (member.id,)
        )
        attended_total = cursor.fetchone()[0] or 0

        conn.close()

        rate_today = (attended_today / total_bosses_today * 100) if total_bosses_today > 0 else 0
        rate_week = (attended_week / total_bosses_week * 100) if total_bosses_week > 0 else 0
        rate_total = (attended_total / total_bosses * 100) if total_bosses > 0 else 0

        embed = discord.Embed(title=f"Статистика посещаемости для {member.display_name}")
        embed.add_field(name="Сегодня", value=f"{attended_today}/{total_bosses_today} ({rate_today:.1f}%)")
        embed.add_field(name="За неделю", value=f"{attended_week}/{total_bosses_week} ({rate_week:.1f}%)")
        embed.add_field(name="За всё время", value=f"{attended_total}/{total_bosses} ({rate_total:.1f}%)")

        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Ошибка в команде boss_rate: {e}")
        await ctx.send("Произошла ошибка при получении статистики")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Неизвестная команда!")
    else:
        print(f"Произошла ошибка: {error}")

if __name__ == "__main__":
    print("Запуск бота...")
    print(f"Токен: {'*' * len(TOKEN) if TOKEN else 'НЕ НАЙДЕН'}")

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("ОШИБКА: Неверный токен! Проверьте токен в файле .env")
    except Exception as e:
        print(f"Критическая ошибка: {e}")