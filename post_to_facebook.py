#!/usr/bin/env python3
"""
Facebook Group Poster v2 — без Selenium, через чистый HTTP + куки.
Используется запрос к Facebook GraphQL (тот же, что и фронтенд).
"""
import os
import sys
import json
import base64
import re
import time
import random
from datetime import datetime
from urllib.parse import quote

import requests

from key_loader import (
    load_premium_keys,
    load_fallback_keys,
    load_light_verified_keys,
    create_public_file,
)


def load_keys():
    """Загрузка ключей — идентично v1."""
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
FB_USER_ID = os.environ.get("FB_USER_ID", "")
# FB_DTSG — anti-CSRF токен Facebook, можно извлечь из кук или страницы
FB_DTSG = os.environ.get("FB_DTSG", "")

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FOLDER = os.path.join(WORK_DIR, "results")
PREMIUM_FOLDER = os.path.join(RESULTS_FOLDER, "premium")
COVER_PUBLIC = os.path.join(WORK_DIR, "cover_public.jpg")

COOKIES_FILE = "/tmp/facebook_cookies.json"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_cookies() -> list:
    """Декодирует куки из B64. Возвращает список dict'ов (name, value, domain...)."""
    if not COOKIES_B64:
        log("❌ FACEBOOK_COOKIES_B64 не установлена")
        return []

    cookies_json = base64.b64decode(COOKIES_B64).decode("utf-8")
    cookies_list = json.loads(cookies_json)

    # Сохраняем для requests
    os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies_list, f)

    log(f"✅ Загружено {len(cookies_list)} кук")
    return cookies_list


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


def extract_fb_dtsg(session: requests.Session) -> str:
    """Извлекает fb_dtsg / token из HTML страницы Facebook."""
    try:
        resp = session.get(
            "https://www.facebook.com/",
            timeout=15,
        )
        text = resp.text

        # fb_dtsg выглядит так: "fb_dtsg":{"token":"abc123","token_type":1}
        # или fb_dtsg":"abc123"
        pattern1 = re.search(r'"fb_dtsg"\s*:\s*\{[^}]*"token"\s*:\s*"([^"]+)"', text)
        if pattern1:
            return pattern1.group(1)

        pattern2 = re.search(r'"fb_dtsg"\s*:\s*"([^"]+)"', text)
        if pattern2:
            return pattern2.group(1)

        # Ищем в куках xs (это тоже token)
        for cookie in session.cookies:
            if cookie.name == "xs":
                return cookie.value

        log("⚠️ fb_dtsg не найден")
        return ""
    except Exception as e:
        log(f"⚠️ Не удалось извлечь fb_dtsg: {e}")
        return ""


def post_to_group_via_graphql(
    session: requests.Session,
    post_text: str,
    file_path: str | None = None,
) -> bool:
    """
    Публикация через внутренний Facebook GraphQL API.
    Использует реальный doc_id: 36949139048065438 (ComposerStoryCreateMutation)
    """
    # 1. Получаем fb_dtsg (anti-CSRF)
    fb_dtsg = extract_fb_dtsg(session)
    if not fb_dtsg:
        fb_dtsg = FB_DTSG

    log(f"🔑 fb_dtsg: {'найден' if fb_dtsg else 'не найден'}")

    # Пробуем нетто-токен (если есть в куках)
    for cookie in session.cookies:
        if cookie.name == "c_user":
            FB_USER_ID_ENV = cookie.value
            break
    else:
        FB_USER_ID_ENV = FB_USER_ID or "61591249905664"

    DOC_ID = "36949139048065438"
    FB_FRIENDLY_NAME = "ComposerStoryCreateMutation"

    # Формируем variables в точности как Facebook фронтенд
    variables = {
        "input": {
            "composer_entry_point": "group",
            "composer_source_surface": "group",
            "composer_type": "group",
            "source": "WWW",
            "message": {
                "text": post_text,
            },
            "audience": {
                "to_id": FB_GROUP_ID,
            },
            "actor_id": FB_USER_ID_ENV,
            "client_mutation_id": str(int(time.time() * 1000)),
            "composer_session_id": f"composer_{int(time.time())}",
            "navigation_store_id": f"nav_{int(time.time())}",
        }
    }

    payload = {
        "av": FB_USER_ID_ENV,
        "__user": FB_USER_ID_ENV,
        "__a": "1",
        "__req": str(random.randint(1, 20)),
        "__hs": "19861.HYP:comet_pkg.2.1.1.1.0",
        "__comet_req": "1",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": FB_FRIENDLY_NAME,
        "variables": json.dumps(variables),
        "doc_id": DOC_ID,
        "fb_dtsg": fb_dtsg,
        "jazoest": "2" + str(random.randint(1000, 9999)),
        "dpr": "2",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": f"https://www.facebook.com/groups/{FB_GROUP_ID}/",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-FB-Friendly-Name": FB_FRIENDLY_NAME,
        "X-FB-LSD": fb_dtsg,
    }

    log(f"📤 GraphQL (doc_id={DOC_ID})...")
    try:
        resp = session.post(
            "https://www.facebook.com/api/graphql/",
            data=payload,
            headers=headers,
            timeout=30,
        )
        log(f"📥 HTTP {resp.status_code}")
        log(f"📄 Тело: {resp.text[:2000]}")

        if resp.status_code == 200:
            # Убираем защитный префикс for (;;);
            body = resp.text
            if body.startswith("for (;;);"):
                body = body[9:]

            try:
                data = json.loads(body)

                # Проверяем на ошибки
                if "error" in data:
                    error_code = data.get("error")
                    error_summary = data.get("errorSummary", "")
                    error_desc = data.get("errorDescription", "")
                    log(f"⚠️ Facebook error {error_code}: {error_summary} — {error_desc}")

                    if error_code == 1357032:
                        log("💡 fb_dtsg невалидный — куки протухли или нужно обновить")
                    return False

                # Парсим post_id
                post_id = None
                try:
                    post_id = data.get("data", {}).get("story_create", {}).get("story", {}).get("post_id")
                except Exception:
                    pass
                if not post_id:
                    try:
                        post_id = data.get("data", {}).get("story_create", {}).get("story", {}).get("id")
                    except Exception:
                        pass
                if not post_id:
                    post_id = re.search(r'"post_id"\s*:\s*"(\d+)"', resp.text)

                if post_id:
                    post_url = f"https://www.facebook.com/groups/{FB_GROUP_ID}/posts/{post_id}"
                    log(f"🔗 Пост: {post_url}")
                    return True

                # Если в ответе есть story_create — успех
                if "story_create" in resp.text:
                    # Ищем любой ID в ответе
                    id_match = re.search(r'"id"\s*:\s*"(\d+)"', resp.text)
                    if id_match:
                        post_url = f"https://www.facebook.com/groups/{FB_GROUP_ID}/posts/{id_match.group(1)}"
                        log(f"🔗 Пост: {post_url}")
                        return True
                    log("✅ Пост создан (story_create в ответе)")
                    return True

                log("⚠️ Ответ не содержит story_create")
                return False

            except json.JSONDecodeError:
                log("⚠️ Ответ не JSON")
                return False
        else:
            log(f"❌ HTTP {resp.status_code}")
            return False
    except Exception as e:
        log(f"❌ Исключение: {e}")
        return False


def main():
    log("=" * 70)
    log("📘 FACEBOOK GROUP POSTER v2 (HTTP-only)")
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

    # 2. Создаём публичный файл (на будущее — прикреплять не можем через HTTP)
    log("\n📄 Создание публичного файла...")
    public_file, public_count = create_public_file(all_keys, key_stats)
    log(f"✅ Создан файл: {public_file} ({public_count} ключей)")

    # 3. Формируем текст
    post_text = build_post_text(total_keys, public_count)
    log(f"\n📝 Текст поста:\n{post_text}\n")

    if DRY_RUN:
        log("⚙️ DRY_RUN: пропускаем отправку")
        return 0

    # 4. Загружаем куки и создаём сессию
    cookies_list = load_cookies()
    if not cookies_list:
        return 1

    session = requests.Session()

    # Ставим куки в session (куки — массив объектов с name/value/domain)
    for cookie in cookies_list:
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        domain = cookie.get("domain", ".facebook.com")
        session.cookies.set(name, value, domain=domain)

    # Устанавливаем домен по умолчанию
    log("🌐 Инициализация сессии...")
    try:
        resp = session.get("https://www.facebook.com/", timeout=15)
        log(f"✅ Facebook загружен: HTTP {resp.status_code}")
    except Exception as e:
        log(f"❌ Не удалось загрузить facebook.com: {e}")
        return 1

    # 5. Пробуем опубликовать (AJAX + GraphQL внутри)
    log("\n🚀 Публикация...")
    success = post_to_group_via_graphql(session, post_text, public_file)

    if success:
        log("\n✅ Пост успешно опубликован!")
        return 0
    else:
        log("\n❌ Не удалось опубликовать пост ни одним методом")
        log("💡 Нужно обновить куки Facebook или получить fb_dtsg вручную")
        return 1


if __name__ == "__main__":
    sys.exit(main())
