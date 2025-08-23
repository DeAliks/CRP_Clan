import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
import io
from PIL import Image
import pytesseract
import re
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance



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

# Создаем папки для хранения данных
os.makedirs('loot_screenshots', exist_ok=True)
os.makedirs('temp_images', exist_ok=True)


# Подключение к БД
def get_db_connection():
    conn = sqlite3.connect('crp_clan.db')
    conn.row_factory = sqlite3.Row
    return conn


# Функция для миграции базы данных
def migrate_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Проверяем существование таблиц и добавляем недостающие колонки
    cursor.execute("PRAGMA table_info(boss_kills)")
    columns = [column[1] for column in cursor.fetchall()]

    # Добавляем недостающие колонки в boss_kills
    if 'is_killed' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN is_killed INTEGER DEFAULT 0")

    if 'respawn_notified' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN respawn_notified INTEGER DEFAULT 0")

    if 'channel_id' not in columns:
        cursor.execute("ALTER TABLE boss_kills ADD COLUMN channel_id INTEGER")

    # Проверяем существование таблицы boss_loot
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

    conn.commit()
    conn.close()

    # Выполняем миграцию для существующих баз данных
    migrate_database()


@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    init_db()
    check_respawns.start()


# Фоновая задача для проверки респавнов боссов
@tasks.loop(minutes=5)
async def check_respawns():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, boss_name, respawn, channel_id 
            FROM boss_kills 
            WHERE respawn_notified = 0 AND is_killed = 1
        ''')

        bosses_to_respawn = cursor.fetchall()
        now = datetime.datetime.now()

        for boss in bosses_to_respawn:
            try:
                respawn_time = datetime.datetime.strptime(boss['respawn'], "%d.%m.%y-%H:%M")

                if now >= respawn_time:
                    channel = bot.get_channel(boss['channel_id'])
                    if channel:
                        await channel.send(
                            f"@everyone\n"
                            f"🔄 БОСС ВОЗРОДИЛСЯ!\n"
                            f"{boss['boss_name']} снова доступен для убийства!\n"
                            f"Используйте команду !spawn для отметки появления."
                        )

                        cursor.execute(
                            'UPDATE boss_kills SET respawn_notified = 1 WHERE id = ?',
                            (boss['id'],)
                        )
                        conn.commit()
            except Exception as e:
                print(f"Ошибка при обработке респавна босса {boss['boss_name']}: {e}")

        conn.close()
    except Exception as e:
        print(f"Ошибка в задаче check_respawns: {e}")


# Функция для обработки изображений с помощью OCR
async def process_image_with_ocr(image_url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    image = Image.open(io.BytesIO(image_data))

                    # Сохраняем временную копию для обработки
                    temp_path = f"temp_images/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    image.save(temp_path)

                    # Используем OCR для извлечения текста
                    text = pytesseract.image_to_string(image, lang='eng')

                    # Ищем паттерны логов дропа
                    loot_pattern = r'\[\d{2}:\d{2}\].+acquired.+from'
                    loot_items = re.findall(loot_pattern, text)

                    return loot_items, temp_path
    except Exception as e:
        print(f"Ошибка при обработке изображения: {e}")
        return [], None


@bot.command()
async def spawn(ctx):
    """Команда для выбора босса через реакции"""
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

    for i in range(len(BOSS_LIST)):
        await message.add_reaction(BOSS_EMOJIS[i])


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    # Обработка выбора босса через реакции
    if str(reaction.emoji) in BOSS_EMOJIS and reaction.message.author == bot.user:
        if not reaction.message.embeds:
            return

        embed = reaction.message.embeds[0]
        if embed.title != "Выберите босса который появился":
            return

        boss_index = BOSS_EMOJIS.index(str(reaction.emoji))
        if boss_index >= len(BOSS_LIST):
            return

        boss_name = BOSS_LIST[boss_index]
        await reaction.message.delete()

        channel = discord.utils.get(reaction.message.guild.channels, name="boss_alert")
        if not channel:
            channel = reaction.message.channel

        message = await channel.send(
            f"@everyone\n"
            f"🔥 БОСС ПОЯВИЛСЯ!\n"
            f"{boss_name} - сейчас появится\n\n"
            f"Поставьте реакцию ✅ для отметки участия на боссе\n\n"
            f"📍 Действия\n"
            f"✅ - Участвую в убийстве босса\n"
            f"💬 - Ответьте на это сообщение со скриншотом дропа чтобы отметить убийство босса"
        )

        await message.add_reaction('✅')

        now = datetime.datetime.now()
        kill_time = (now + datetime.timedelta(minutes=5)).strftime("%d.%m.%y-%H:%M")
        respawn_hours = BOSS_RESPAWNS[boss_name]
        respawn_time = (now + datetime.timedelta(hours=respawn_hours)).strftime("%d.%m.%y-%H:%M")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO boss_kills (boss_name, kill_time, respawn, message_id, channel_id) VALUES (?, ?, ?, ?, ?)',
            (boss_name, kill_time, respawn_time, message.id, channel.id)
        )
        conn.commit()
        conn.close()

        return

    # Обработка участия в убийстве босса
    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT id, is_killed FROM boss_kills WHERE message_id = ?',
            (reaction.message.id,)
        )
        boss_kill = cursor.fetchone()

        if boss_kill and not boss_kill['is_killed']:
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


@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Обработка ответов на сообщения о боссах
    if message.reference and message.reference.message_id:
        try:
            replied_message = await message.channel.fetch_message(message.reference.message_id)

            if (replied_message.author == bot.user and
                    replied_message.channel.name == "boss_alert" and
                    "🔥 БОСС ПОЯВИЛСЯ!" in replied_message.content):

                conn = get_db_connection()
                cursor = conn.cursor()

                cursor.execute(
                    'SELECT id, is_killed FROM boss_kills WHERE message_id = ?',
                    (replied_message.id,)
                )
                boss_kill = cursor.fetchone()

                if boss_kill and not boss_kill['is_killed']:
                    # Помечаем босса как убитого
                    cursor.execute(
                        'UPDATE boss_kills SET is_killed = 1 WHERE id = ?',
                        (boss_kill['id'],)
                    )

                    # Обрабатываем вложения (скриншоты дропа)
                    loot_items = []
                    screenshot_path = None

                    if message.attachments:
                        for attachment in message.attachments:
                            if any(attachment.filename.lower().endswith(ext) for ext in
                                   ['.png', '.jpg', '.jpeg', '.gif', '.bmp']):
                                # Сохраняем скриншот
                                screenshot_path = f"loot_screenshots/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{attachment.filename}"
                                await attachment.save(screenshot_path)

                                # Анализируем скриншот с помощью OCR
                                items, _ = await process_image_with_ocr(attachment.url)
                                loot_items.extend(items)

                    # Сохраняем информацию о дропе в базу данных
                    loot_text = "\n".join(loot_items) if loot_items else "Не удалось распознать дроп"

                    cursor.execute(
                        'INSERT INTO boss_loot (boss_kill_id, user_id, username, screenshot_path, loot_text, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        (boss_kill['id'], message.author.id, str(message.author), screenshot_path, loot_text,
                         datetime.datetime.now().strftime("%d.%m.%y-%H:%M"))
                    )

                    conn.commit()

                    # Удаляем реакцию ✅ и добавляем ☠️
                    await replied_message.clear_reactions()
                    await replied_message.add_reaction('☠️')

                    # Редактируем сообщение о боссе
                    new_content = replied_message.content.replace(
                        "💬 - Ответьте на это сообщение со скриншотом дропа чтобы отметить убийство босса",
                        "☠️ - Босс убит! Отметки участия закрыты."
                    )
                    await replied_message.edit(content=new_content)

                    # Отправляем подтверждение с информацией о дропе
                    if loot_items:
                        loot_info = "\n".join([f"• {item}" for item in loot_items[:5]])  # Показываем первые 5 предметов
                        if len(loot_items) > 5:
                            loot_info += f"\n• ... и еще {len(loot_items) - 5} предметов"

                        await message.channel.send(
                            f"{message.author.mention} отметил(а) убийство босса!\n"
                            f"📦 Выбитые предметы:\n{loot_info}"
                        )
                    else:
                        await message.channel.send(
                            f"{message.author.mention} отметил(а) убийство босса!\n"
                            f"📦 Не удалось распознать предметы из скриншота."
                        )

                conn.close()
        except Exception as e:
            print(f"Ошибка при обработке ответа на сообщение: {e}")

    await bot.process_commands(message)


# Команда для просмотра дропа с босса
@bot.command()
async def loot(ctx, boss_kill_id: int = None):
    """Показывает дроп с указанного убийства босса"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if boss_kill_id:
        # Показываем дроп для конкретного убийства
        cursor.execute(
            'SELECT bl.*, bk.boss_name FROM boss_loot bl JOIN boss_kills bk ON bl.boss_kill_id = bk.id WHERE bl.boss_kill_id = ?',
            (boss_kill_id,)
        )
        loot_data = cursor.fetchall()

        if not loot_data:
            await ctx.send("Не найдено данных о дропе для указанного ID убийства.")
            conn.close()
            return

        embed = discord.Embed(title=f"Дроп с {loot_data[0]['boss_name']}", color=0x00ff00)

        for loot in loot_data:
            loot_text = loot['loot_text'] if loot['loot_text'] else "Не удалось распознать дроп"
            embed.add_field(
                name=f"От {loot['username']}",
                value=f"```{loot_text[:500]}...```" if len(loot_text) > 500 else f"```{loot_text}```",
                inline=False
            )

        await ctx.send(embed=embed)
    else:
        # Показываем последние 5 убийств с дропом
        cursor.execute('''
            SELECT bk.id, bk.boss_name, bk.kill_time, COUNT(bl.id) as loot_count 
            FROM boss_kills bk 
            LEFT JOIN boss_loot bl ON bk.id = bl.boss_kill_id 
            WHERE bk.is_killed = 1 
            GROUP BY bk.id 
            ORDER BY bk.kill_time DESC 
            LIMIT 5
        ''')
        recent_kills = cursor.fetchall()

        if not recent_kills:
            await ctx.send("Нет данных об убийствах боссов.")
            conn.close()
            return

        embed = discord.Embed(title="Последние убийства боссов", color=0x00ff00)

        for kill in recent_kills:
            embed.add_field(
                name=f"{kill['boss_name']} ({kill['kill_time']})",
                value=f"ID: {kill['id']}, Дропов: {kill['loot_count']}",
                inline=False
            )

        embed.set_footer(text="Используйте !loot <ID> для просмотра деталей дропа")
        await ctx.send(embed=embed)

    conn.close()


@bot.command()
async def boss_rate(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.datetime.now().strftime("%d.%m.%y")
    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills WHERE kill_time LIKE ?',
        (f'{today}%',)
    )
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
    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills WHERE kill_time >= ?',
        (week_ago,)
    )
    total_bosses_week = cursor.fetchone()[0] or 0

    cursor.execute(
        '''SELECT COUNT(*) FROM boss_attendance 
           INNER JOIN boss_kills ON boss_attendance.boss_kill_id = boss_kills.id 
           WHERE boss_attendance.user_id = ? AND boss_attendance.attended = 1 
           AND boss_kills.kill_time >= ?''',
        (member.id, week_ago)
    )
    attended_week = cursor.fetchone()[0] or 0

    cursor.execute(
        'SELECT COUNT(*) FROM boss_kills'
    )
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


async def process_image_with_ocr(image_url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    image = Image.open(io.BytesIO(image_data))

                    # Конвертируем в RGB если нужно
                    if image.mode != 'RGB':
                        image = image.convert('RGB')

                    # Улучшаем качество изображения для лучшего распознавания
                    image = enhance_image_for_ocr(image)

                    # Сохраняем временную копию для обработки
                    temp_path = f"temp_images/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    image.save(temp_path, 'PNG')

                    # Используем OCR для извлечения текста
                    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist="[]0123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "'
                    text = pytesseract.image_to_string(image, lang='eng', config=custom_config)

                    # Ищем паттерны логов дропа
                    loot_pattern = r'\[\d{2}:\d{2}\].+acquired.+from'
                    loot_items = re.findall(loot_pattern, text)

                    return loot_items, temp_path
    except Exception as e:
        print(f"Ошибка при обработке изображения: {e}")
        return [], None


def enhance_image_for_ocr(image):
    """Улучшает изображение для лучшего распознавания текста"""
    # Увеличиваем контрастность
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # Увеличиваем резкость
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)

    # Применяем фильтр для уменьшения шума
    image = image.filter(ImageFilter.MedianFilter(3))

    # Конвертируем в numpy array для обработки
    img_array = np.array(image)

    # Целевые цвета из HEX в RGB
    background_color = np.array([15, 15, 18])  # #0f0f12
    time_color = np.array([150, 150, 150])  # #969696
    text_color = np.array([184, 184, 183])  # #b8b8b7
    drop_colors = [
        np.array([13, 108, 198]),  # #0d6cc6
        np.array([73, 20, 116]),  # #491474
        np.array([8, 153, 35]),  # #089923
        np.array([173, 6, 7])  # #ad0607
    ]

    # Создаем маску для текста (все целевые цвета)
    text_mask = np.zeros(img_array.shape[:2], dtype=bool)

    # Добавляем цвета текста в маску
    for color in [time_color, text_color] + drop_colors:
        color_diff = np.sqrt(np.sum((img_array - color) ** 2, axis=2))
        text_mask = text_mask | (color_diff < 50)  # допуск 50

    # Создаем новое изображение с белым фоном и черным текстом
    enhanced_array = np.ones_like(img_array) * 255  # белый фон
    enhanced_array[text_mask] = [0, 0, 0]  # черный текст

    # Конвертируем обратно в PIL Image
    enhanced_image = Image.fromarray(enhanced_array.astype('uint8'))

    # Дополнительное улучшение контраста
    enhancer = ImageEnhance.Contrast(enhanced_image)
    enhanced_image = enhancer.enhance(10.0)

    return enhanced_image

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
        print(f"Произошла ошибка при запуске бота: {e}")#//test