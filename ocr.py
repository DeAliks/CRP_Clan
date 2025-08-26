import os
import re
import logging
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import numpy as np
import colorsys
from datetime import datetime

# Настройка путей
INPUT_IMAGE_PATH = r"C:\Users\Greed\Downloads\OCR\Origin Image\1.png"
OUTPUT_DIR = r"C:\Users\Greed\Downloads\OCR\Filtred Image"
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Создаем выходную директорию, если её нет
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Настройка логирования
log_file = os.path.join(OUTPUT_DIR, f"ocr_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def save_debug_image(image, name):
    """Сохраняет изображение для отладки"""
    debug_path = os.path.join(OUTPUT_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png")
    image.save(debug_path, 'PNG')
    logger.info(f"Сохранено изображение: {debug_path}")
    return debug_path


def save_text_result(text, name):
    """Сохраняет текстовый результат"""
    text_path = os.path.join(OUTPUT_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.txt")
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(text)
    logger.info(f"Сохранен текстовый результат: {text_path}")
    return text_path


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

    # Сохраняем промежуточные текстовые результаты
    save_text_result(text_gray, "gray_method_text")
    save_text_result(text_hsv, "hsv_method_text")

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

    # Сохраняем финальный текстовый результат
    final_text_path = save_text_result(best_text, f"final_text_{method}")

    return best_img, best_text, method


def process_image_with_ocr(image_path):
    """Основная функция обработки изображения"""
    try:
        logger.info(f"Начинаем обработку изображения: {image_path}")

        # Загружаем изображение
        image = Image.open(image_path)

        # Конвертируем в RGB если нужно
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Улучшаем качество изображения для лучшего распознавания
        enhanced_image, text, method = enhance_image_for_ocr(image)

        # Извлекаем предметы из текста
        items = extract_items(text)

        # Формируем результат
        result_text = f"Метод обработки: {method}\n\n"
        result_text += f"Полный текст:\n{text}\n\n"
        result_text += f"Извлеченные предметы ({len(items)}):\n"

        for i, item in enumerate(items, 1):
            result_text += f"{i}. {item}\n"

        # Сохраняем финальный результат
        final_text_path = save_text_result(result_text, "final_result")

        return result_text, items

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        return f"Ошибка: {e}", []


if __name__ == "__main__":
    logger.info("Запуск OCR обработки изображения")
    logger.info(f"Входной файл: {INPUT_IMAGE_PATH}")
    logger.info(f"Выходная директория: {OUTPUT_DIR}")

    # Проверяем существование входного файла
    if not os.path.exists(INPUT_IMAGE_PATH):
        logger.error(f"Входной файл не найден: {INPUT_IMAGE_PATH}")
        exit(1)

    # Обрабатываем изображение
    result_text, items = process_image_with_ocr(INPUT_IMAGE_PATH)

    logger.info("Обработка завершена")
    print(f"Результат сохранен в: {OUTPUT_DIR}")
    print(f"Найдено {len(items)} предметов:")
    for i, item in enumerate(items, 1):
        print(f"{i}. {item}")