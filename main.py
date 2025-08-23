import discord
from discord.ext import commands
import sqlite3
import datetime
import os
from dotenv import load_dotenv
import asyncio

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("ОШИБКА: Токен не найден!")
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
    "Sapgirus - 80 LV": 168,  # 7 дней (168 часов)
    "Neutro 80 LV": 168,  # 7 дней
    "Clemantis - 70 LV": 168  # 7 дней
}

# Список боссов для выбора
BOSS_LIST = [
    "Venatus - 60 LV",
    "Viorent - 65 LV",
    "Ego - 70 LV",
    "Livera - 75 LV",
    "Araneo - 75 LV",
    "Undomiel - 80 LV",
    "Lady Dalia 85 LV",
    "Amentis - 88 LV",
    "Baron - 88 LV",
    "Wannitas - 93 LV",
    "Metus - 93 LV",
    "Sapgirus - 80 LV",
    "Neutro 80 LV",
    "Clemantis - 70 LV"
]

# Эмодзи для выбора боссов
BOSS_EMOJIS = [
    '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣',
    '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟',
    '⏸️', '🔯', '✳️', '🔄'
]


# Подключение к БД
def get_db_connection():
    conn = sqlite3.connect('crp_clan.db')
    conn.row_factory = sqlite3.Row
    return conn


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
            message_id INTEGER,
            is_killed INTEGER DEFAULT 0
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

    conn.commit()
    conn.close()


@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    init_db()


@bot.command()
async def spawn(ctx):
    """Команда для выбора босса через реакции"""
    # Создаем embed с выбором боссов
    embed = discord.Embed(
        title="Выберите босса который появился",
        description="Поставьте реакцию с номером босса:",
        color=0x00ff00
    )

    for i, boss in enumerate(BOSS_LIST):
        embed.add_field(
            name=f"{BOSS_EMOJIS[i]} {boss}",
            value=f"Респавн: {BOSS_RESPAWNS[boss]} часов",
            inline=False
        )

    message = await ctx.send(embed=embed)

    # Добавляем реакции для выбора
    for i in range(len(BOSS_LIST)):
        await message.add_reaction(BOSS_EMOJIS[i])


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    # Обработка выбора босса через реакции
    if str(reaction.emoji) in BOSS_EMOJIS and reaction.message.author == bot.user:
        # Проверяем, что это сообщение с выбором босса
        if not reaction.message.embeds:
            return

        embed = reaction.message.embeds[0]
        if embed.title != "Выберите босса который появился":
            return

        # Определяем выбранного босса
        boss_index = BOSS_EMOJIS.index(str(reaction.emoji))
        if boss_index >= len(BOSS_LIST):
            return

        boss_name = BOSS_LIST[boss_index]

        # Удаляем сообщение с выбором
        await reaction.message.delete()

        # Отправляем уведомление о боссе
        channel = discord.utils.get(reaction.message.guild.channels, name="boss_alert")
        if not channel:
            channel = reaction.message.channel

        message = await channel.send(
            f"@everyone\n"
            f"🔥 БОСС ПОЯВИЛСЯ!\n"
            f"{boss_name} - сейчас появится\n\n"
            f"Поставьте реакцию ✅ для отметки участия на боссе\n"
            f"Поставьте реакцию ❌ для отметки убийства босса\n\n"
            f"📍 Действия\n"
            f"✅ - Участвую в убийстве босса\n"
            f"❌ - убили босса"
        )

        await message.add_reaction('✅')
        await message.add_reaction('❌')

        # Расчет времени
        now = datetime.datetime.now()
        kill_time = (now + datetime.timedelta(minutes=5)).strftime("%d.%m.%y-%H:%M")
        respawn_hours = BOSS_RESPAWNS[boss_name]
        respawn_time = (now + datetime.timedelta(hours=respawn_hours)).strftime("%d.%m.%y-%H:%M")

        # Сохранение в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO boss_kills (boss_name, kill_time, respawn, message_id) VALUES (?, ?, ?, ?)',
            (boss_name, kill_time, respawn_time, message.id)
        )
        conn.commit()
        conn.close()

        return

    # Обработка участия в убийстве босса
    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверяем, не убит ли уже босс
        cursor.execute(
            'SELECT id, is_killed FROM boss_kills WHERE message_id = ?',
            (reaction.message.id,)
        )
        boss_kill = cursor.fetchone()

        if boss_kill and not boss_kill['is_killed']:
            # Проверяем, есть ли уже пользователь
            cursor.execute(
                'SELECT * FROM boss_attendance WHERE boss_kill_id = ? AND user_id = ?',
                (boss_kill['id'], user.id)
            )
            existing = cursor.fetchone()

            if not existing:
                cursor.execute(
                    'INSERT INTO boss_attendance (boss_kill_id, user_id, username, attended) VALUES (?, ?, ?, 1)',
                    (boss_kill['id'], user.id, str(user))
                )
            else:
                cursor.execute(
                    'UPDATE boss_attendance SET attended = 1 WHERE boss_kill_id = ? AND user_id = ?',
                    (boss_kill['id'], user.id)
                )

            conn.commit()
        conn.close()

    # Обработка отметки об убийстве босса
    if str(reaction.emoji) == "❌" and reaction.message.channel.name == "boss_alert":
        conn = get_db_connection()
        cursor = conn.cursor()

        # Помечаем босса как убитого
        cursor.execute(
            'UPDATE boss_kills SET is_killed = 1 WHERE message_id = ?',
            (reaction.message.id,)
        )
        conn.commit()
        conn.close()

        # Удаляем реакции, чтобы нельзя было больше отмечаться
        message = reaction.message
        await message.clear_reactions()


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
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
                (boss_kill['id'], user.id)
            )
            conn.commit()
        conn.close()


@bot.command()
async def boss_rate(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    conn = get_db_connection()
    cursor = conn.cursor()

    # Статистика за сегодня
    today = datetime.datetime.now().strftime("%d.%m.%y")
    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills WHERE kill_time LIKE ?',
        (f'{today}%',)
    )
    total_bosses_today = cursor.fetchone()[0]

    cursor.execute(
        '''SELECT COUNT(*) FROM boss_attendance 
           INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
           WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1 
           AND boss_kills.kill_time LIKE ?''',
        (member.id, f'{today}%')
    )
    attended_today = cursor.fetchone()[0]

    # Статистика за неделю
    week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%d.%m.%y")
    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills WHERE kill_time >= ?',
        (week_ago,)
    )
    total_bosses_week = cursor.fetchone()[0]

    cursor.execute(
        '''SELECT COUNT(*) FROM boss_attendance 
           INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
           WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1 
           AND boss_kills.kill_time >= ?''',
        (member.id, week_ago)
    )
    attended_week = cursor.fetchone()[0]

    # Общая статистика
    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills'
    )
    total_bosses = cursor.fetchone()[0]

    cursor.execute(
        '''SELECT COUNT(*) FROM boss_attendance 
           INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
           WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1''',
        (member.id,)
    )
    attended_total = cursor.fetchone()[0]

    conn.close()

    # Расчет процентов
    rate_today = (attended_today / total_bosses_today * 100) if total_bosses_today > 0 else 0
    rate_week = (attended_week / total_bosses_week * 100) if total_bosses_week > 0 else 0
    rate_total = (attended_total / total_bosses * 100) if total_bosses > 0 else 0

    # Формирование ответа
    embed = discord.Embed(title=f"Статистика посещаемости для {member.display_name}")
    embed.add_field(name="Сегодня", value=f"{attended_today}/{total_bosses_today} ({rate_today:.1f}%)")
    embed.add_field(name="За неделю", value=f"{attended_week}/{total_bosses_week} ({rate_week:.1f}%)")
    embed.add_field(name="За всё время", value=f"{attended_total}/{total_bosses} ({rate_total:.1f}%)")

    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Неизвестная команда!")
    else:
        print(f"Произошла ошибка: {error}")


# Запуск бота
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Произошла ошибка при запуске бота: {e}")


 # test