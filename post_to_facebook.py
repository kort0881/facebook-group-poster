#!/usr/bin/env python3
"""
Автоматический постинг VPN-ключей в Facebook Group.
Использует Selenium + undetected-chromedriver для браузерной автоматизации.

Переменные окружения:
  FACEBOOK_COOKIES_B64  — Base64-кодированный JSON с куками Facebook
  FB_GROUP_ID           — ID группы (по умолчанию: 2478873955927710)
  FB_DRY_RUN            — "1" для тестового прогона (только логи, без публикации)
"""
import os
import sys
import json
import base64
import time
import random
from datetime import datetime
from pathlib import Path

from key_loader import (
    load_premium_keys,
    load_fallback_keys,
    load_light_verified_keys,
    create_public_file,
)

# --- КОНФИГУРАЦИЯ ---
DRY_RUN = os.environ.get("FB_DRY_RUN", "0") == "1"
COOKIES_B64 = os.environ.get("FACEBOOK_COOKIES_B64", "")
FB_GROUP_ID = os.environ.get("FB_GROUP_ID", "2478873955927710")
FB_GROUP_URL = f"https://www.facebook.com/groups/{FB_GROUP_ID}"

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FOLDER = os.path.join(WORK_DIR, "results")
PREMIUM_FOLDER = os.path.join(RESULTS_FOLDER, "premium")
COVER_PUBLIC = os.path.join(WORK_DIR, "cover_public.jpg")


def random_sleep(min_s=1.0, max_s=3.0):
    """Человеческая задержка между действиями."""
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_keys():
    """Загрузка ключей — идентично proxy-auto-checker."""
    all_keys = []
    key_stats = None
    source_info = ""

    if os.path.exists(PREMIUM_FOLDER):
        log("📁 Ищем ключи в results/premium/...")
        all_keys, key_stats = load_premium_keys()
        if all_keys:
            source_info = "results/premium (elite + premium + good)"
            log(f"✅ Загружено из results/premium: {len(all_keys)} ключей")

    if not all_keys:
        log("📁 Premium пусто, ищем verified/semi_dead...")
        all_keys, filename, source = load_fallback_keys()
        if all_keys:
            source_info = f"{source} ({filename})"
            log(f"✅ Fallback: {len(all_keys)} ключей из {filename}")
        else:
            log("⚠️ verified/semi_dead нет, пробуем checked/latest/verified.txt...")
            all_keys = load_light_verified_keys()
            if all_keys:
                source_info = "checked/latest/verified.txt (TCP-only)"
                log(f"✅ Fallback: {len(all_keys)} ключей из checked/latest/verified.txt")

    return all_keys, key_stats, source_info


def build_post_text(total_keys, public_count):
    """Формирует текст поста (без упоминания @vlesstrojan)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"🔥 Проверенные прокси-ключи\n"
        f"📅 {now}\n"
        f"📦 В файле: {public_count}\n"
        f"📊 Всего ключей: {total_keys}\n"
        f"📡 VLESS | VMess | Trojan | SS\n\n"
        f"#vpn #proxy #vless #vmess #trojan #shadowsocks #бесплатно"
    )


def setup_browser():
    """Настройка undetected-chromedriver с подавлением логов."""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument(f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")

    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    # Подавляем вывод ChromeDriver
    import logging
    logging.getLogger("undetected_chromedriver").setLevel(logging.WARNING)

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(30)

    # Подменяем webdriver detection
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en'] });
        """
    })
    return driver


def login_with_cookies(driver):
    """Загружает cookies Facebook из переменной окружения."""
    if not COOKIES_B64:
        log("❌ FACEBOOK_COOKIES_B64 не установлена")
        return False

    try:
        cookies_json = base64.b64decode(COOKIES_B64).decode("utf-8")
        cookies = json.loads(cookies_json)
    except Exception as e:
        log(f"❌ Ошибка декодирования кук: {e}")
        return False

    # Сначала заходим на facebook.com, чтобы установить домен
    log("🌐 Загружаем facebook.com для установки кук...")
    driver.get("https://www.facebook.com")
    random_sleep(2, 4)

    for cookie in cookies:
        # Пропускаем лишние поля
        c = {
            "name": cookie.get("name"),
            "value": cookie.get("value"),
            "domain": cookie.get("domain", ".facebook.com"),
            "path": cookie.get("path", "/"),
            "secure": cookie.get("secure", True),
        }
        if cookie.get("httpOnly"):
            c["httpOnly"] = True
        if cookie.get("sameSite"):
            c["sameSite"] = cookie["sameSite"]
        if "expiry" in cookie:
            c["expiry"] = cookie["expiry"]
        elif "expirationDate" in cookie:
            c["expiry"] = int(cookie["expirationDate"])

        # Убираем куки не для facebook.com
        if "facebook" not in c["domain"] and "fbcdn" not in c["domain"]:
            continue

        try:
            driver.add_cookie(c)
        except Exception:
            pass  # Игнорируем проблемные куки

    log(f"✅ Загружено {len(cookies)} кук")
    return True


def post_to_facebook(driver, post_text, image_path, file_path):
    """
    Основная функция: публикует пост в группу Facebook.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, 20)

    # Если есть изображение — загружаем через прямой URL с ?sk=photos
    # Иначе используем стандартную страницу группы
    log(f"🌐 Открываем группу: {FB_GROUP_URL}")
    driver.get(FB_GROUP_URL)
    random_sleep(4, 6)

    # 1. Пытаемся найти и нажать кнопку "Создать публикацию"
    log("🔍 Ищем поле ввода...")
    try:
        # Ждём загрузки страницы группы
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@data-pagelet='Group']"))
        )
        log("✅ Страница группы загружена")
    except Exception:
        log("⚠️ data-pagelet=Group не найден")

    # Универсальный поиск кнопки создания поста через JS
    create_post_btn = driver.execute_script("""
        // Стратегия 1: ищем текстовую кнопку с ключевыми словами
        const keywords = ['нового', 'write', 'what', 'create', 'поделиться', 'публикаци'];
        const links = document.querySelectorAll('a[role="button"], div[role="button"], span[role="button"]');
        for (const el of links) {
            const text = (el.textContent || '').toLowerCase();
            if (keywords.some(k => text.includes(k)) && el.offsetParent !== null) {
                return el;
            }
        }
        // Стратегия 2: первый видимый role="button" внутри области группы
        const group = document.querySelector('[data-pagelet="Group"]');
        if (group) {
            const buttons = group.querySelectorAll('[role="button"]');
            for (const btn of buttons) {
                if (btn.offsetParent !== null) return btn;
            }
        }
        // Стратегия 3: любой видимый role="button" на странице
        const allBtns = document.querySelectorAll('[role="button"]');
        for (const btn of allBtns) {
            if (btn.offsetParent !== null && btn.querySelector('span')) return btn;
        }
        return null;
    """)

    if create_post_btn:
        log("✅ Найдена кнопка создания поста")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", create_post_btn)
        random_sleep(0.5, 1)

        try:
            create_post_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", create_post_btn)

        log("✅ Кнопка нажата, ждём редактора...")
        random_sleep(3, 5)
    else:
        log("⚠️ Кнопка не найдена, переходим на страницу создания поста...")
        driver.get(f"https://www.facebook.com/groups/{FB_GROUP_ID}/publish")
        random_sleep(4, 6)

    # 2. Ищем текстовый редактор
    log("✏️ Ищем текстовый редактор...")
    text_area = None

    # Сначала ждём модалку
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        log("✅ Модальное окно открыто")
    except Exception:
        log("⚠️ Модальное окно не найдено")

    # Ищем textbox внутри модалки или напрямую
    text_selectors = [
        "//div[@role='dialog']//div[@role='textbox' and @contenteditable='true']",
        "//div[@role='dialog']//div[@contenteditable='true']",
        "//div[@role='textbox' and @contenteditable='true']",
        "//div[@contenteditable='true']",
        "//div[@data-lexical-editor='true']",
        "//div[@class='notranslate']//p[@data-lexical-text='true']",
    ]

    for sel in text_selectors:
        try:
            text_area = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, sel))
            )
            if text_area and text_area.is_displayed():
                log(f"✅ Найден редактор: {sel}")
                break
        except Exception:
            continue

    # JS fallback для поиска редактора
    if not text_area:
        log("⚠️ Селекторы не сработали, ищем contenteditable через JS...")
        text_area = driver.execute_script("""
            const editables = document.querySelectorAll('[contenteditable="true"]');
            for (const el of editables) {
                if (el.offsetParent !== null) {
                    // Проверяем что это именно текстовая область, не просто кнопка
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 30) return el;
                }
            }
            // Очень широкий fallback
            const allEdit = document.querySelectorAll('[contenteditable]');
            for (const el of allEdit) {
                if (el.offsetParent !== null) return el;
            }
            return null;
        """)
        if text_area:
            log("✅ Найден contenteditable через JS")

    if not text_area:
        log("❌ Не найден текстовый редактор")
        driver.save_screenshot("fb_error_textbox.png")
        with open("fb_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        return False

    # Пробуем кликнуть и ввести текст
    try:
        text_area.click()
    except Exception:
        driver.execute_script("arguments[0].click();", text_area)

    random_sleep(0.5, 1.5)

    # Очищаем поле если там есть placeholder
    try:
        text_area.clear()
    except Exception:
        pass

    log("✏️ Вводим текст поста...")
    for line in post_text.split("\n"):
        text_area.send_keys(line)
        text_area.send_keys("\n")
        random_sleep(0.2, 0.5)

    log("✅ Текст введён")
    random_sleep(1, 2)

    # 3. Загружаем изображение (опционально)
    if image_path and os.path.exists(image_path):
        log(f"🖼️ Загружаем изображение: {image_path}")
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(image_path))
            log("✅ Изображение отправлено")
            random_sleep(2, 4)
        except Exception as e:
            log(f"⚠️ Не удалось загрузить изображение: {e}")
    else:
        log("⚠️ Изображение не найдено, пропускаем")

    random_sleep(1, 2)

    # 4. Прикрепляем файл с ключами
    if file_path and os.path.exists(file_path):
        log(f"📎 Прикрепляем файл: {file_path}")
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(os.path.abspath(file_path))
            log("✅ Файл прикреплён")
            random_sleep(2, 3)
        except Exception as e:
            log(f"⚠️ Ошибка прикрепления файла: {e}")
    else:
        log("⚠️ Файл не найден, пропускаем")

    random_sleep(1, 2)

    # 5. Публикуем
    log("🚀 Публикуем...")
    publish_btn = driver.execute_script("""
        // Ищем кнопку отправки в модалке
        const dialog = document.querySelector('[role="dialog"]');
        const candidates = dialog ? dialog.querySelectorAll('[role="button"]') : document.querySelectorAll('[role="button"]');
        const keywords = ['опубликовать', 'publish', 'post', 'отправить', 'share'];
        for (const btn of candidates) {
            const text = (btn.textContent || '').toLowerCase().trim();
            if (keywords.some(k => text === k || text.includes(k))) {
                if (btn.offsetParent !== null) return btn;
            }
        }
        // Fallback: последняя видимая кнопка в модалке
        if (dialog) {
            const btns = dialog.querySelectorAll('div[role="button"]');
            for (let i = btns.length - 1; i >= 0; i--) {
                if (btns[i].offsetParent !== null) return btns[i];
            }
        }
        return null;
    """)

    if publish_btn:
        log("✅ Найдена кнопка публикации")
        try:
            publish_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", publish_btn)
        random_sleep(3, 5)
        log("✅ Пост опубликован!")
        return True
    else:
        log("❌ Не найдена кнопка публикации")
        driver.save_screenshot("fb_error_publish.png")
        return False


def main():
    log("=" * 70)
    log("📘 FACEBOOK GROUP POSTER v1.0")
    log("=" * 70)

    if DRY_RUN:
        log("⚙️ Режим DRY_RUN: публикация не будет выполнена\n")

    if not COOKIES_B64:
        log("❌ FACEBOOK_COOKIES_B64 не установлена")
        return 1

    # 1. Загружаем ключи
    log("\n📥 Загрузка ключей...")
    all_keys, key_stats, source_info = load_keys()

    if not all_keys:
        log("❌ Нет ключей для публикации")
        return 1

    total_keys = len(all_keys)
    log(f"📦 Всего ключей: {total_keys}")
    log(f"📂 Источник: {source_info}")

    # 2. Создаём публичный файл
    log("\n📄 Создание публичного файла...")
    public_file, public_count = create_public_file(all_keys, key_stats)
    log(f"✅ Создан файл: {public_file} ({public_count} ключей)")

    # 3. Формируем текст
    post_text = build_post_text(total_keys, public_count)
    log(f"\n📝 Текст поста:\n{post_text}\n")

    if DRY_RUN:
        log("⚙️ DRY_RUN: пропускаем браузер")
        return 0

    # 4. Запускаем браузер и публикуем
    log("\n🌐 Запуск браузера...")
    driver = None
    try:
        driver = setup_browser()
        log("✅ Браузер запущен")

        login_with_cookies(driver)
        random_sleep(1, 2)

        success = post_to_facebook(driver, post_text, COVER_PUBLIC, public_file)
        if success:
            log("\n✅ Пост успешно опубликован в Facebook Group!")
            return 0
        else:
            log("\n❌ Не удалось опубликовать пост")
            return 1

    except Exception as e:
        log(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if driver:
            random_sleep(2, 3)
            try:
                log("📸 Скриншот результата...")
                driver.save_screenshot("fb_final_screenshot.png")
            except Exception:
                pass
            log("🧹 Закрываем браузер...")
            driver.quit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
