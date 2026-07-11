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
    """Извлекает fb_dtsg / token из страницы Facebook."""
    try:
        resp = session.get(
            "https://www.facebook.com/api/graphql/",
            params={"fb_api_req_friendly_name": "GroupsCometFeedRegularStoriesQuery"},
            timeout=15,
        )
        # Пробуем найти токен в ответе
        text = resp.text
        # Ищем fb_dtsg в HTML
        token_match = re.search(r'"fb_dtsg"\s*:\s*"([^"]+)"', text)
        if token_match:
            return token_match.group(1)

        # Пробуем из кук
        for cookie in session.cookies:
            if cookie.name == "xs":
                return cookie.value

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
    Использует тот же эндпоинт, что и SPA-фронтенд Facebook.
    """
    # 1. Получаем fb_dtsg (anti-CSRF)
    fb_dtsg = extract_fb_dtsg(session)
    if not fb_dtsg:
        # fallback: из переменной окружения
        fb_dtsg = FB_DTSG

    log(f"🔑 fb_dtsg: {'найден' if fb_dtsg else 'не найден'}")

    # 2. Формируем запрос к GraphQL
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": f"https://www.facebook.com/groups/{FB_GROUP_ID}/",
        "Sec-Fetch-Site": "same-origin",
    }

    # GraphQL-запрос для создания поста в группе
    # Используем ComposerPlutoAttachmentSurfaceMutation
    variables = {
        "input": {
            "group_id": FB_GROUP_ID,
            "message": post_text,
            "source": "WWW",
            "composer_entry_point": "group",
            "composer_session_id": f"composer_{int(time.time())}",
            "composer_type": "group",
            "client_mutation_id": str(int(time.time() * 1000)),
            "audience": {"to_id": FB_GROUP_ID},
            "navigation_store_id": f"nav_{int(time.time())}",
        },
        "displayCommentsCreateFormContext": {},
    }

    payload = {
        "fb_api_req_friendly_name": "ComposerPlutoAttachmentSurfaceCreateMutation",
        "variables": json.dumps(variables),
        "doc_id": "5095407912680046",  # ID GraphQL-мутации (стабильный)
        "fb_dtsg": fb_dtsg,
        "av": FB_USER_ID or "0",
    }

    # Убираем None значения
    payload = {k: v for k, v in payload.items() if v}

    log("📤 Отправка GraphQL-запроса...")
    try:
        resp = session.post(
            "https://www.facebook.com/api/graphql/",
            data=payload,
            headers=headers,
            timeout=30,
        )
        log(f"📥 Ответ: HTTP {resp.status_code}")
        log(f"📄 Тело: {resp.text[:2000]}")

        if resp.status_code == 200:
            try:
                data = resp.json()

                # Парсим post_id из ответа GraphQL
                post_id = None
                try:
                    post_id = data.get("data", {}).get("story_create", {}).get("story", {}).get("post_id")
                except Exception:
                    pass
                if not post_id:
                    try:
                        post_id = data.get("data", {}).get("post_create", {}).get("post", {}).get("id")
                    except Exception:
                        pass
                if not post_id:
                    # Ищем post_id в тексте ответа
                    import re as re_mod
                    match = re_mod.search(r'"post_id"\s*:\s*"(\\d+)"', resp.text)
                    if match:
                        post_id = match.group(1)

                if post_id:
                    post_url = f"https://www.facebook.com/groups/{FB_GROUP_ID}/posts/{post_id}"
                    log(f"🔗 Пост: {post_url}")
                    return True
                else:
                    log("ℹ️ post_id не найден — возможно, мутация не сработала")
                    return False
                if "error" in data:
                    log(f"⚠️ Ошибка GraphQL: {data['error']}")
                    return False
            except json.JSONDecodeError:
                pass

            # Если ответ не JSON — возможно, успех
            if "post_id" in resp.text or "story_create" in resp.text:
                return True

        # Если 200 или 302 — успех
        if resp.status_code in (200, 302):
            return True

        log(f"❌ Ошибка: {resp.text[:500]}")
        return False
    except Exception as e:
        log(f"❌ Исключение: {e}")
        return False


def try_simple_post(session: requests.Session, post_text: str) -> bool:
    """
    Самый простой способ — POST на /a/group/post.php (старый endpoint).
    Facebook всё ещё поддерживает его для совместимости.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": f"https://www.facebook.com/groups/{FB_GROUP_ID}/",
    }

    data = {
        "fb_dtsg": extract_fb_dtsg(session),
        "target": FB_GROUP_ID,
        "xhpc_targetid": FB_GROUP_ID,
        "xhpc_message": post_text,
        "xhpc_ismeta": "1",
        "xhpc_context": "group",
        "source": "WWW",
    }

    try:
        resp = session.post(
            "https://www.facebook.com/ajax/group/post/stories/",
            data=data,
            headers=headers,
            timeout=30,
        )
        log(f"📥 Simple POST ответ: HTTP {resp.status_code}")

        if resp.status_code in (200, 302):
            log("✅ Пост опубликован (simple POST)!")
            return True

        log(f"⚠️ Simple POST не сработал: {resp.text[:300]}")
        return False
    except Exception as e:
        log(f"❌ Simple POST исключение: {e}")
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

    # 5. Пробуем опубликовать
    log("\n🚀 Публикация через GraphQL...")
    success = post_to_group_via_graphql(session, post_text, public_file)

    if not success:
        log("\n🔄 Пробуем Simple POST...")
        success = try_simple_post(session, post_text)

    if success:
        log("\n✅ Пост успешно опубликован!")
        return 0
    else:
        log("\n❌ Не удалось опубликовать пост ни одним методом")
        log("💡 Нужно обновить куки Facebook или получить fb_dtsg вручную")
        return 1


if __name__ == "__main__":
    sys.exit(main())
