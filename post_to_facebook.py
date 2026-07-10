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
    options.add_argument("--disable-notifications")
    options.add_argument(f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

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
    log(f"🌐 Открываем группу: {FB_GROUP_URL}")
    driver.get(FB_GROUP_URL)
    random_sleep(3, 5)

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, 20)

    # 1. Находим поле "Что у вас нового?"
    log("🔍 Ищем поле ввода...")
    try:
        # Пробуем разные селекторы
        selectors = [
            "//span[contains(text(), 'Чем вы хотите поделиться')]/..",
            "//span[contains(text(), 'What')]/..",
            "//div[@role='button']//span[contains(text(), 'у вас нового')]/..",
            "//div[@role='button']//span[contains(text(), 'нового')]/..",
            "//div[@aria-label='Создать публикацию']",
            "//div[@aria-label='Create a post']",
            "//div[@role='button']//span[contains(text(), 'Write something')]/..",
            "//form[@method='POST']//div[@role='button']",
            "//div[@data-pagelet='Group']//div[@role='button']",
        ]
        create_post_btn = None
        for sel in selectors:
            try:
                create_post_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                log(f"✅ Найден селектор: {sel}")
                break
            except Exception:
                continue

        if not create_post_btn:
            # Пробуем просто кликнуть в центр страницы
            log("⚠️ Селекторы не сработали, кликаем в центр...")
            create_post_btn = driver.find_element(By.TAG_NAME, "body")

        create_post_btn.click()
        random_sleep(2, 4)
    except Exception as e:
        log(f"❌ Не удалось открыть редактор поста: {e}")
        # Сохраняем скриншот для отладки
        driver.save_screenshot("fb_error_create_post.png")
        log("📸 Скриншот сохранён: fb_error_create_post.png")
        return False

    # 2. Вводим текст
    log("✏️ Вводим текст поста...")
    try:
        text_selectors = [
            "//div[@role='textbox' and @aria-label]",
            "//div[@contenteditable='true']",
            "//div[@data-lexical-editor='true']",
            "//div[@class='notranslate']//p",
            "//div[@aria-label[contains(.,'публикац') or contains(.,'post') or contains(.,'Write') or contains(.,'нового')]]",
            "//div[@contenteditable='true' and @role='textbox']",
            "//div[@contenteditable='true' and @spellcheck='true']",
            "//*[@contenteditable='true']",
        ]
        text_area = None
        for sel in text_selectors:
            try:
                text_area = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                if text_area:
                    log(f"✅ Найден редактор: {sel}")
                    break
            except Exception:
                continue

        if not text_area:
            # Пробуем найти любой видимый contenteditable
            log("⚠️ Селекторы не сработали, ищем contenteditable элементы...")
            all_editable = driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']")
            for el in all_editable:
                if el.is_displayed():
                    text_area = el
                    log("✅ Найден contenteditable элемент")
                    break

        if not text_area:
            log("❌ Не найден текстовый редактор")
            # Сохраняем скриншот и HTML для отладки
            driver.save_screenshot("fb_error_textbox.png")
            with open("fb_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            log("📸 Скриншот: fb_error_textbox.png")
            log("📄 HTML страницы сохранён в fb_page_source.html")
            return False

        text_area.click()
        random_sleep(0.5, 1.5)

        # Печатаем с человеческой скоростью
        for line in post_text.split("\n"):
            text_area.send_keys(line)
            text_area.send_keys("\n")
            random_sleep(0.3, 0.8)

        log("✅ Текст введён")
    except Exception as e:
        log(f"❌ Ошибка ввода текста: {e}")
        return False

    random_sleep(1, 2)

    # 3. Загружаем изображение
    if image_path and os.path.exists(image_path):
        log(f"🖼️ Загружаем изображение: {image_path}")
        try:
            # Кликаем "Фото/видео"
            photo_btn_selectors = [
                "//div[@aria-label='Фото/видео']",
                "//div[@aria-label='Photo/video']",
                "//span[text()='Фото/видео']/..",
                "//span[text()='Photo/video']/..",
                "//div[@role='button']//i[contains(@data-visualcompletion, 'css')]/../../..",
            ]
            photo_btn = None
            for sel in photo_btn_selectors:
                try:
                    photo_btn = driver.find_element(By.XPATH, sel)
                    break
                except Exception:
                    continue

            if photo_btn:
                # Ищем input[type=file] внутри
                file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                file_input.send_keys(os.path.abspath(image_path))
                log("✅ Изображение загружено через input[type=file]")
                random_sleep(2, 4)
            else:
                log("⚠️ Кнопка фото не найдена, пробуем input[type=file] напрямую")
                try:
                    file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                    file_input.send_keys(os.path.abspath(image_path))
                    random_sleep(2, 4)
                except Exception as e2:
                    log(f"⚠️ Не удалось загрузить фото: {e2}")
        except Exception as e:
            log(f"⚠️ Ошибка загрузки изображения: {e}")
    else:
        log("⚠️ Изображение не найдено, пропускаем")

    random_sleep(1, 2)

    # 4. Прикрепляем файл с ключами
    if file_path and os.path.exists(file_path):
        log(f"📎 Прикрепляем файл: {file_path}")
        try:
            # Ищем все input[type=file] — второй может быть для файла
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if len(file_inputs) >= 2:
                file_inputs[1].send_keys(os.path.abspath(file_path))
                log("✅ Файл прикреплён")
            elif file_inputs:
                file_inputs[0].send_keys(os.path.abspath(file_path))
                log("✅ Файл отправлен через первый input")
            else:
                log("⚠️ Не найдены input[type=file]")
        except Exception as e:
            log(f"⚠️ Ошибка прикрепления файла: {e}")

    random_sleep(1, 2)

    # 5. Публикуем
    log("🚀 Публикуем...")
    try:
        publish_selectors = [
            "//span[text()='Опубликовать']/..",
            "//span[text()='Publish']/..",
            "//span[text()='Post']/..",
            "//div[@aria-label='Опубликовать']",
            "//div[@aria-label='Post']",
            "//div[@role='button']//span[contains(text(), 'Опубликовать')]/..",
            "//div[@role='button']//span[contains(text(), 'Publish')]/..",
        ]
        publish_btn = None
        for sel in publish_selectors:
            try:
                publish_btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                if publish_btn:
                    log(f"✅ Найдена кнопка публикации: {sel}")
                    break
            except Exception:
                continue

        if not publish_btn:
            log("❌ Не найдена кнопка публикации")
            driver.save_screenshot("fb_error_publish.png")
            return False

        publish_btn.click()
        random_sleep(3, 5)

        log("✅ Пост опубликован!")
        return True
    except Exception as e:
        log(f"❌ Ошибка публикации: {e}")
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
