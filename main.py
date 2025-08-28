import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
import io
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import pytesseract
import re
import numpy as np
import colorsys
import logging
import threading
from database import init_db, get_db_connection

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    logger.error("Токен не найден!")
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
    "Sapgirus - 80 LV": 168,
    "Neutro 80 LV": 168,
    "Clemantis - 70 LV": 168
}

# Список боссов для выбора
BOSS_LIST = list(BOSS_RESPAWNS.keys())

# Эмодзи для выбора боссов
BOSS_EMOJIS = [
    '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣',
    '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟',
    '⏸️', '🔯', '✳️', '🔄'
]

# Создаем папки для хранения данных
os.makedirs('loot_screenshots', exist_ok=True)
os.makedirs('temp_images', exist_ok=True)
os.makedirs('debug_images', exist_ok=True)  # Для отладочных изображений


# Запуск веб-сервера в отдельном потоке
def run_web_app():
    import web_app
    web_app.app.run()


@bot.event
async def on_ready():
    logger.info(f'Бот {bot.user} запущен!')
    init_db()
    check_respawns.start()

    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_app)
    web_thread.daemon = True
    web_thread.start()
    logger.info("Веб-сервер запущен на http://0.0.0.0:8080")
# Подключение к БД
def get_db_connection():
    conn = sqlite3.connect('crp_clan.db')
    conn.row_factory = sqlite3.Row
    return conn


# Функция для миграции базы данных
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

    migrate_database()


@bot.event
async def on_ready():
    logger.info(f'Бот {bot.user} запущен!')
    init_db()
    check_respawns.start()


# Фоновая задача для проверки респавнов боссов
@tasks.loop(minutes=5)
async def check_respawns():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Получаем только актуальные записи (последнее убийство для каждого босса)
        cursor.execute('''
            SELECT bk1.* 
            FROM boss_kills bk1
            INNER JOIN (
                SELECT boss_name, MAX(id) as max_id
                FROM boss_kills
                GROUP BY boss_name
            ) bk2 ON bk1.id = bk2.max_id
            WHERE bk1.respawn_notified = 0 AND bk1.is_killed = 1
        ''')

        bosses_to_respawn = cursor.fetchall()
        now = datetime.datetime.now()

        for boss in bosses_to_respawn:
            try:
                respawn_time = datetime.datetime.strptime(boss['respawn'], "%d.%m.%y-%H:%M")

                if now >= respawn_time:
                    channel = bot.get_channel(boss['channel_id'])
                    if channel:
                        # Отправляем прямое уведомление о появлении босса
                        message = await channel.send(
                            f"@everyone\n"
                            f"🔥 БОСС ПОЯВИЛСЯ!\n"
                            f"{boss['boss_name']} - сейчас появится\n\n"
                            f"Поставьте реакцию ✅ для отметки участия на боссе\n\n"
                            f"📍 Действия\n"
                            f"✅ - Участвую в убийстве босса\n"
                            f"💬 - Ответьте на это сообщение со скриншотом дропа чтобы отметить убийство босса"
                        )

                        await message.add_reaction('✅')

                        # Создаем новую запись в базе данных для нового появления босса
                        new_kill_time = (now + datetime.timedelta(minutes=5)).strftime("%d.%m.%y-%H:%M")
                        respawn_hours = BOSS_RESPAWNS.get(boss['boss_name'], 24)  # Значение по умолчанию 24 часа
                        new_respawn_time = (now + datetime.timedelta(hours=respawn_hours)).strftime("%d.%m.%y-%H:%M")

                        cursor.execute(
                            'INSERT INTO boss_kills (boss_name, kill_time, respawn, message_id, channel_id) VALUES (?, ?, ?, ?, ?)',
                            (boss['boss_name'], new_kill_time, new_respawn_time, message.id, channel.id)
                        )

                        # Помечаем старую запись как обработанную
                        cursor.execute(
                            'UPDATE boss_kills SET respawn_notified = 1 WHERE id = ?',
                            (boss['id'],)
                        )

                        conn.commit()
                        logger.info(f"Автоматически создано уведомление о появлении босса {boss['boss_name']}")
            except Exception as e:
                logger.error(f"Ошибка при обработке респавна босса {boss['boss_name']}: {e}")

        conn.close()
    except Exception as e:
        logger.error(f"Ошибка в задаче check_respawns: {e}")

def save_debug_image(image, name):
    """Сохраняет изображение для отладки"""
    debug_path = f"debug_images/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
    image.save(debug_path, 'PNG')
    return debug_path


def extract_items(text):
    """Извлекает названия предметов между 'acquired' и 'from'"""
    logger.info("Извлекаем названия предметов из текста")

    # Регулярное выражение для поиска текста между "acquired" и "from"
    pattern = r'acquired\s+(.*?)\s+from'
    items = re.findall(pattern, text, re.IGNORECASE)

    # Очищаем результаты
    cleaned_items = []
    for item in items:
        # Убираем лишние пробелы и переносы строк
        cleaned_item = ' '.join(item.split())
        # Убираем возможные точки и запятые в конце
        cleaned_item = cleaned_item.rstrip('.,')
        cleaned_items.append(cleaned_item)

    logger.info(f"Найдено {len(cleaned_items)} предметов")
    return cleaned_items


def enhance_gray(image):
    """Вариант 1: простая бинаризация"""
    logger.info("Применяем серый метод обработки")
    img = image.convert("L")  # в серый
    img = ImageOps.autocontrast(img)
    img = ImageOps.invert(img)  # текст становится чёрным
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    return img


def enhance_hsv(image):
    """Вариант 2: HSV фильтрация цветного текста"""
    logger.info("Применяем HSV метод обработки")
    img = image.convert("RGB")
    img_array = np.array(img)

    # RGB → HSV
    hsv_array = np.zeros_like(img_array, dtype=float)
    for y in range(img_array.shape[0]):
        for x in range(img_array.shape[1]):
            r, g, b = img_array[y, x] / 255.0
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            hsv_array[y, x] = [h * 360, s * 100, v * 100]

    # Диапазоны цветов (H, S, V)
    ranges = [
        ((0, 10), (50, 100), (30, 100)),  # красный 1
        ((340, 360), (50, 100), (30, 100)),  # красный 2
        ((80, 150), (30, 100), (30, 100)),  # зелёный
        ((180, 260), (30, 100), (30, 100)),  # синий
        ((260, 320), (30, 100), (30, 100)),  # фиолетовый
        ((30, 70), (30, 100), (30, 100)),  # жёлтый
        ((0, 360), (0, 20), (40, 100)),  # серый/белый обычный текст
    ]

    # Маска текста
    h, s, v = hsv_array[:, :, 0], hsv_array[:, :, 1], hsv_array[:, :, 2]
    text_mask = np.zeros(img_array.shape[:2], dtype=bool)
    for h_range, s_range, v_range in ranges:
        mask = ((h >= h_range[0]) & (h <= h_range[1]) &
                (s >= s_range[0]) & (s <= s_range[1]) &
                (v >= v_range[0]) & (v <= v_range[1]))
        text_mask |= mask

    # Чёрный текст на белом фоне
    enhanced_array = np.ones_like(img_array) * 255
    enhanced_array[text_mask] = [0, 0, 0]
    return Image.fromarray(enhanced_array.astype("uint8"))


def enhance_image_for_ocr(image):
    """Гибрид: пробуем два метода и выбираем лучший"""
    # Сохраняем оригинал
    original_path = save_debug_image(image, "01_original")
    logger.info(f"Сохранено исходное изображение: {original_path}")

    # Пробуем оба метода
    gray_variant = enhance_gray(image)
    hsv_variant = enhance_hsv(image)

    # Сохраняем оба варианта для отладки
    gray_path = save_debug_image(gray_variant, "02_gray_method")
    logger.info(f"Сохранено изображение после серого метода: {gray_path}")
    hsv_path = save_debug_image(hsv_variant, "03_hsv_method")
    logger.info(f"Сохранено изображение после HSV метода: {hsv_path}")

    # Проверяем OCR на обоих
    custom_config = r'--oem 3 --psm 6'
    text_gray = pytesseract.image_to_string(gray_variant, lang='eng', config=custom_config)
    text_hsv = pytesseract.image_to_string(hsv_variant, lang='eng', config=custom_config)

    # Выбираем лучший по количеству символов
    if len(text_hsv.strip()) > len(text_gray.strip()):
        best_img = hsv_variant
        best_text = text_hsv
        method = "HSV"
        logger.info(f"Выбран метод HSV, количество символов: {len(text_hsv.strip())}")
    else:
        best_img = gray_variant
        best_text = text_gray
        method = "GRAY"
        logger.info(f"Выбран метод GRAY, количество символов: {len(text_gray.strip())}")

    # Сохраняем финальное изображение
    final_path = save_debug_image(best_img, f"04_final_{method}")
    logger.info(f"Сохранено финальное изображение: {final_path}")

    return best_img, best_text, method


async def process_image_with_ocr(image_url):
    try:
        logger.info(f"Начинаем обработку изображения: {image_url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    image = Image.open(io.BytesIO(image_data))

                    # Конвертируем в RGB если нужно
                    if image.mode != 'RGB':
                        image = image.convert('RGB')

                    # Улучшаем качество изображения для лучшего распознавания
                    enhanced_image, text, method = enhance_image_for_ocr(image)

                    # Извлекаем предметы из текста
                    items = extract_items(text)

                    # Сохраняем временную копию для обработки
                    temp_path = f"temp_images/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    enhanced_image.save(temp_path, 'PNG')
                    logger.info(f"Сохранено временное изображение: {temp_path}")

                    # Используем OCR для извлечения текста с разными настройками
                    configs = [
                        r'--oem 3 --psm 6',
                        r'--oem 3 --psm 7',
                        r'--oem 3 --psm 8',
                        r'--oem 3 --psm 13'
                    ]

                    best_text = text
                    best_config = ""

                    for config in configs:
                        try:
                            new_text = pytesseract.image_to_string(enhanced_image, lang='eng', config=config)
                            logger.info(f"Распознанный текст с конфигом {config}:\n{new_text}")

                            # Если этот конфиг дал больше текста, сохраняем его
                            if len(new_text) > len(best_text):
                                best_text = new_text
                                best_config = config
                        except Exception as e:
                            logger.error(f"Ошибка при распознавании с конфигом {config}: {e}")

                    logger.info(f"Лучший конфиг: {best_config}")
                    logger.info(f"Лучший распознанный текст:\n{best_text}")

                    # Извлекаем предметы из лучшего текста
                    final_items = extract_items(best_text)

                    return final_items, temp_path
                else:
                    logger.error(f"Ошибка загрузки изображения: статус {resp.status}")
                    return [], None
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
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

    logger.info(f"Пользователь {ctx.author} использовал команду !spawn")


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
        logger.info(f"Пользователь {user} выбрал босса: {boss_name}")

        channel = discord.utils.get(reaction.message.guild.channels, name="boss_alert")
        if not channel:
            channel = reaction.message.channel

        conn = get_db_connection()
        cursor = conn.cursor()

        # Помечаем все предыдущие записи этого босса как неактуальные
        cursor.execute(
            'UPDATE boss_kills SET is_killed = 1, respawn_notified = 1 WHERE boss_name = ? AND is_killed = 0',
            (boss_name,)
        )

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

        cursor.execute(
            'INSERT INTO boss_kills (boss_name, kill_time, respawn, message_id, channel_id) VALUES (?, ?, ?, ?, ?)',
            (boss_name, kill_time, respawn_time, message.id, channel.id)
        )
        conn.commit()
        conn.close()

        logger.info(f"Создано уведомление о боссе {boss_name} (ID сообщения: {message.id})")
        return

    # Обработка участия в убийстве босса
    if str(reaction.emoji) == "✅" and reaction.message.channel.name == "boss_alert":
        conn = get_db_connection()
        cursor = conn.cursor()

        # Получаем только актуальную запись (последнее появление босса)
        cursor.execute('''
            SELECT id, is_killed 
            FROM boss_kills 
            WHERE message_id = ? 
            AND id = (
                SELECT MAX(id) 
                FROM boss_kills 
                WHERE boss_name = (
                    SELECT boss_name 
                    FROM boss_kills 
                    WHERE message_id = ?
                )
            )
        ''', (reaction.message.id, reaction.message.id))

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
                logger.info(f"Пользователь {user} добавлен к участию в убийстве босса (ID: {boss_kill['id']})")
            else:
                cursor.execute(
                    'UPDATE boss_attendance SET attended = 1 WHERE boss_kill_id = ? AND user_id = ?',
                    (boss_kill['id'], user.id)
                )
                logger.info(f"Пользователь {user} подтвердил участие в убийстве босса (ID: {boss_kill['id']})")

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
            logger.info(f"Пользователь {user} отменил участие в убийстве босса (ID: {boss_kill['id']})")
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

                # Получаем только актуальную запись (последнее появление босса)
                cursor.execute('''
                    SELECT id, is_killed 
                    FROM boss_kills 
                    WHERE message_id = ? 
                    AND id = (
                        SELECT MAX(id) 
                        FROM boss_kills 
                        WHERE boss_name = (
                            SELECT boss_name 
                            FROM boss_kills 
                            WHERE message_id = ?
                        )
                    )
                ''', (replied_message.id, replied_message.id))

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
                                logger.info(f"Сохранен скриншот дропа: {screenshot_path}")

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
                        # Формируем полный список предметов (без ограничения в 5 элементов)
                        loot_info = "\n".join([f"• {item}" for item in loot_items])

                        # Если предметов много, разбиваем на несколько сообщений (ограничение Discord - 2000 символов)
                        if len(loot_info) > 1900:
                            # Разбиваем на части
                            parts = []
                            current_part = ""

                            for item in loot_items:
                                item_line = f"• {item}\n"
                                if len(current_part) + len(item_line) > 1900:
                                    parts.append(current_part)
                                    current_part = item_line
                                else:
                                    current_part += item_line

                            if current_part:
                                parts.append(current_part)

                            # Отправляем первое сообщение с информацией
                            await message.channel.send(
                                f"{message.author.mention} отметил(а) убийство босса!\n"
                                f"📦 Выбитые предметы (часть 1 из {len(parts)}):\n{parts[0]}"
                            )

                            # Отправляем остальные части
                            for i, part in enumerate(parts[1:], 2):
                                await message.channel.send(
                                    f"📦 Выбитые предметы (часть {i} из {len(parts)}):\n{part}"
                                )
                        else:
                            await message.channel.send(
                                f"{message.author.mention} отметил(а) убийство босса!\n"
                                f"📦 Выбитые предметы:\n{loot_info}"
                            )

                        logger.info(f"Успешно распознаны предметы: {loot_items}")
                    else:
                        await message.channel.send(
                            f"{message.author.mention} отметил(а) убийство босса!\n"
                            f"📦 Не удалось распознать предметы из скриншота. Пожалуйста, проверьте качество изображения."
                        )
                        logger.warning(f"Не удалось распознать предметы из скриншота {screenshot_path}")

                conn.close()
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа на сообщение: {e}")

    await bot.process_commands(message)




# Команда для просмотра дропа с босса
@bot.command()
async def loot(ctx, boss_kill_id: int = None):
    """Показывает дроп с указанного убийства босса"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if boss_kill_id:
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
        logger.info(f"Показан дроп для убийства босса ID: {boss_kill_id}")
    else:
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
        logger.info("Показаны последние убийства боссов")

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
        (member.id, f'{today}%',)
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
    logger.info(f"Показана статистика для пользователя {member.display_name}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Неизвестная команда!")
    else:
        logger.error(f"Произошла ошибка: {error}")


# Запуск бота
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")