#!/usr/bin/env python3
"""
Facebook Group Poster v4 — Playwright (новый headless, Facebook не видит).
Публикует текст + файл через настоящий браузер.
"""
import os
import sys
import json
import base64
import time
import random
from datetime import datetime

from key_loader import (
    load_premium_keys,
    load_fallback_keys,
    load_light_verified_keys,
    create_public_file,
)


def load_keys():
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


# --- КОНФИГУРАЦИЯ ---
DRY_RUN = os.environ.get("FB_DRY_RUN", "0") == "1"
COOKIES_B64 = os.environ.get("FACEBOOK_COOKIES_B64", "")
FB_GROUP_ID = os.environ.get("FB_GROUP_ID", "2478873955927710")

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FOLDER = os.path.join(WORK_DIR, "results")
PREMIUM_FOLDER = os.path.join(RESULTS_FOLDER, "premium")
COVER_PUBLIC = os.path.join(WORK_DIR, "cover_public.jpg")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def build_post_text(total_keys, public_count):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"🔥 Проверенные прокси-ключи\n"
        f"📅 {now}\n"
        f"📦 В файле: {public_count}\n"
        f"📊 Всего ключей: {total_keys}\n"
        f"📡 VLESS | VMess | Trojan | SS\n\n"
        f"#vpn #proxy #vless #vmess #trojan #shadowsocks #бесплатно"
    )


async def post_with_playwright(post_text: str, file_path: str | None = None) -> bool:
    """Публикация через Playwright (Facebook не детектит)."""
    from playwright.async_api import async_playwright

    cookies = []
    if COOKIES_B64:
        try:
            cookies = json.loads(base64.b64decode(COOKIES_B64).decode("utf-8"))
            log(f"✅ Загружено {len(cookies)} кук")
        except Exception as e:
            log(f"❌ Ошибка загрузки кук: {e}")
            return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )

        # Ставим куки
        for c in cookies:
            try:
                cookie = {
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ".facebook.com"),
                    "path": c.get("path", "/"),
                }
                if c.get("secure", True):
                    cookie["secure"] = True
                if c.get("httpOnly"):
                    cookie["httpOnly"] = True
                if "expiry" in c:
                    cookie["expires"] = c["expiry"]
                elif "expirationDate" in c:
                    cookie["expires"] = int(c["expirationDate"])

                if "facebook" not in cookie["domain"] and "fbcdn" not in cookie["domain"]:
                    continue
                await context.add_cookies([cookie])
            except Exception:
                pass

        page = await context.new_page()

        try:
            # Загружаем группу
            url = f"https://www.facebook.com/groups/{FB_GROUP_ID}/"
            log(f"🌐 Открываем: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Пробуем найти кнопку создания поста
            log("🔍 Ищем поле ввода...")

            # Стратегия: ищем ссылку на создание поста
            create_selectors = [
                'a[href*="composer"]',
                'a[href*="publish"]',
                '[role="button"]:has-text("нового")',
                '[role="button"]:has-text("Write")',
                '[role="button"]:has-text("What")',
                '[role="button"]:has-text("поделиться")',
                '[data-pagelet="Group"] [role="button"]',
                '//div[@role="button"]//span[contains(text(), "нового")]/..',
                '//div[@role="button"]//span[contains(text(), "Write")]/..',
            ]

            create_btn = None
            for sel in create_selectors:
                try:
                    if sel.startswith("//"):
                        from playwright.async_api import expect
                        create_btn = page.locator(sel).first
                    else:
                        create_btn = page.locator(sel).first

                    if await create_btn.is_visible(timeout=3000):
                        log(f"✅ Найдена кнопка: {sel}")
                        break
                    create_btn = None
                except Exception:
                    create_btn = None

            if not create_btn:
                log("⚠️ Кнопка не найдена, пробуем прямой URL...")
                await page.goto(
                    f"https://www.facebook.com/groups/{FB_GROUP_ID}/publish",
                    wait_until="networkidle",
                    timeout=30000,
                )
                await page.wait_for_timeout(3000)
            else:
                await create_btn.click()
                await page.wait_for_timeout(3000)

            # Ищем редактор
            log("✏️ Ищем редактор...")
            editor = None
            editor_selectors = [
                '[role="textbox"][contenteditable="true"]',
                '[contenteditable="true"]',
                '[data-lexical-editor="true"]',
                '[role="dialog"] [contenteditable="true"]',
                'div[role="dialog"] div[contenteditable="true"]',
            ]

            for sel in editor_selectors:
                try:
                    editor = page.locator(sel).first
                    if await editor.is_visible(timeout=5000):
                        log(f"✅ Найден редактор: {sel}")
                        break
                    editor = None
                except Exception:
                    editor = None

            if not editor:
                log("❌ Редактор не найден")
                await page.screenshot(path="fb_error_editor.png")
                return False

            await editor.click()
            await page.wait_for_timeout(500)

            # Вводим текст
            log("✏️ Вводим текст...")
            for line in post_text.split("\n"):
                await editor.type(line, delay=50)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(200)

            log("✅ Текст введён")

            # Прикрепляем файл если есть
            if file_path and os.path.exists(file_path):
                log(f"📎 Прикрепляем файл: {file_path}")
                try:
                    file_input = page.locator('input[type="file"]').first
                    if await file_input.is_visible(timeout=3000):
                        await file_input.set_input_files(file_path)
                        log("✅ Файл прикреплён")
                        await page.wait_for_timeout(2000)
                except Exception as e:
                    log(f"⚠️ Ошибка файла: {e}")

            await page.wait_for_timeout(1000)

            # Ищем кнопку публикации
            log("🚀 Ищем кнопку публикации...")
            publish_selectors = [
                '[role="button"]:has-text("Опубликовать")',
                '[role="button"]:has-text("Publish")',
                '[role="button"]:has-text("Post")',
                '[role="dialog"] [role="button"]:has-text("Опубликовать")',
                '[role="dialog"] [role="button"]:has-text("Publish")',
                '[role="dialog"] div[role="button"]:last-child',
            ]

            publish_btn = None
            for sel in publish_selectors:
                try:
                    publish_btn = page.locator(sel).first
                    if await publish_btn.is_visible(timeout=3000):
                        log(f"✅ Найдена кнопка: {sel}")
                        break
                    publish_btn = None
                except Exception:
                    publish_btn = None

            if not publish_btn:
                log("❌ Кнопка публикации не найдена")
                await page.screenshot(path="fb_error_publish.png")
                return False

            await publish_btn.click()
            await page.wait_for_timeout(3000)

            log("✅ Пост опубликован!")
            await page.screenshot(path="fb_success.png")
            return True

        except Exception as e:
            log(f"❌ Ошибка: {e}")
            try:
                await page.screenshot(path="fb_error.png")
            except Exception:
                pass
            return False
        finally:
            await browser.close()


def main():
    log("=" * 70)
    log("📘 FACEBOOK GROUP POSTER v4 (Playwright)")
    log("=" * 70)

    if DRY_RUN:
        log("⚙️ Режим DRY_RUN\n")

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

    # 3. Текст поста
    post_text = build_post_text(total_keys, public_count)
    log(f"\n📝 Текст поста:\n{post_text}\n")

    if DRY_RUN:
        log("⚙️ DRY_RUN: пропускаем")
        return 0

    # 4. Публикуем через Playwright
    log("\n🚀 Публикация через Playwright...")
    import asyncio
    success = asyncio.run(post_with_playwright(post_text, public_file))

    if success:
        log("\n✅ Пост опубликован!")
        return 0
    else:
        log("\n❌ Не удалось опубликовать")
        return 1


if __name__ == "__main__":
    sys.exit(main())
