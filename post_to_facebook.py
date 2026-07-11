#!/usr/bin/env python3
"""
Facebook Group Poster v3 — HTTP-only, GraphQL с полной структурой.
"""
import os
import sys
import json
import base64
import re
import time
import random
import uuid
from datetime import datetime

import requests

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
FB_USER_ID = os.environ.get("FB_USER_ID", "61591249905664")
FB_DTSG = os.environ.get("FB_DTSG", "")

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FOLDER = os.path.join(WORK_DIR, "results")
PREMIUM_FOLDER = os.path.join(RESULTS_FOLDER, "premium")
COVER_PUBLIC = os.path.join(WORK_DIR, "cover_public.jpg")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_cookies() -> list:
    if not COOKIES_B64:
        log("❌ FACEBOOK_COOKIES_B64 не установлена")
        return []

    cookies_json = base64.b64decode(COOKIES_B64).decode("utf-8")
    cookies_list = json.loads(cookies_json)
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


def extract_fb_dtsg_and_lsd(session: requests.Session) -> tuple:
    """Извлекает fb_dtsg и lsd из HTML страницы Facebook."""
    try:
        resp = session.get("https://www.facebook.com/", timeout=15)
        html = resp.text
        log(f"📄 HTML: {len(html)} символов")

        fb_dtsg = ""
        lsd = ""

        # Ищем все ServerJS блоки с токенами
        # Facebook 2026 хранит токены в __bootloader_data__ или ServerJS

        # Стратегия 1: ищем lsd/req_token в __bootloader_data__
        m = re.search(r'__bootloader_data__\s*=\s*(\{[^;]+\})', html)
        if m:
            boot = m.group(1)
            m2 = re.search(r'"lsd"\s*:\s*"([^"]+)"', boot)
            if m2:
                lsd = m2.group(1)
                log(f"✅ lsd (bootloader): {lsd[:15]}...")
            m2 = re.search(r'"fb_dtsg"\s*:\s*"([^"]+)"', boot)
            if m2:
                fb_dtsg = m2.group(1)
                log(f"✅ fb_dtsg (bootloader): {fb_dtsg[:15]}...")
            m2 = re.search(r'"token"\s*:\s*"([^"]+)"', boot)
            if m2 and not lsd:
                lsd = m2.group(1)
                log(f"✅ lsd (bootloader token): {lsd[:15]}...")

        # Стратегия 2: ищем "__req" + "lsd" в JSON-data блоках data-ft
        if not lsd:
            import html as _html
            m = re.search(r'data-ft=["\']([^"\']+)["\']', html)
            if m:
                ft_data = _html.unescape(m.group(1))
                m2 = re.search(r'"lsd"\s*:\s*"([^"]+)"', ft_data)
                if m2:
                    lsd = m2.group(1)
                    log(f"✅ lsd (data-ft): {lsd[:15]}...")

        # Стратегия 3: ищем в JSON-LD или script[type="application/json"]
        if not lsd or not fb_dtsg:
            scripts = re.findall(r'<script[^>]*>(\{[^<]+\})</script>', html)
            for script in scripts[:5]:  # первые 5 блоков
                if '"lsd"' in script:
                    m = re.search(r'"lsd"\s*:\s*"([^"]+)"', script)
                    if m and not lsd:
                        lsd = m.group(1)
                        log(f"✅ lsd (script json): {lsd[:15]}...")
                if '"fb_dtsg"' in script:
                    m = re.search(r'"fb_dtsg"\s*:\s*"([^"]+)"', script)
                    if m and not fb_dtsg:
                        fb_dtsg = m.group(1)
                        log(f"✅ fb_dtsg (script json): {fb_dtsg[:15]}...")

        # Стратегия 4: большой data-json блок
        if not lsd:
            m = re.search(r'data-json=["\']([^"\']{100,})["\']', html)
            if m:
                raw = _html.unescape(m.group(1))
                m2 = re.search(r'"lsd"\s*:\s*"([^"]+)"', raw)
                if m2:
                    lsd = m2.group(1)
                    log(f"✅ lsd (data-json): {lsd[:15]}...")

        # Fallback fb_dtsg: xs cookie
        if not fb_dtsg:
            for cookie in session.cookies:
                if cookie.name == "xs":
                    from urllib.parse import unquote
                    fb_dtsg = unquote(cookie.value)
                    log(f"ℹ️ fb_dtsg из xs: {fb_dtsg[:15]}...")

        return fb_dtsg, lsd
    except Exception as e:
        log(f"⚠️ Ошибка извлечения токенов: {e}")
        return FB_DTSG, ""


def gen_attribution_id():
    ts = int(time.time() * 1000)
    rnd = random.randint(100000, 999999)
    return f"CometGroupDiscussionRoot.react,comet.group,via_cold_start,{ts},{rnd},2361831622,,"


def build_graphql_payload(post_text: str, fb_dtsg: str, lsd: str) -> dict:
    """Формирует полный payload для GraphQL (ComposerStoryCreateMutation)."""
    composer_session_id = str(uuid.uuid4())

    variables = {
        "input": {
            "composer_entry_point": "inline_composer",
            "composer_source_surface": "group",
            "composer_type": "group",
            "logging": {
                "composer_session_id": composer_session_id,
            },
            "source": "WWW",
            "message": {
                "ranges": [],
                "text": post_text,
            },
            "with_tags_ids": None,
            "inline_activities": [],
            "text_format_preset_id": "0",
            "group_flair": {"flair_id": None},
            "attachments": [],  # без фото
            "composed_text": {
                "block_data": ["{}"],
                "block_depths": [0],
                "block_types": [0],
                "blocks": [""],
                "entities": ["[]"],
                "entity_map": "{}",
                "inline_styles": ["[]"],
            },
            "navigation_data": {
                "attribution_id_v2": gen_attribution_id(),
            },
            "tracking": [None],
            "event_share_metadata": {"surface": "newsfeed"},
            "audience": {"to_id": FB_GROUP_ID},
            "actor_id": FB_USER_ID,
            "client_mutation_id": str(int(time.time() * 1000)),
        },
        "feedLocation": "GROUP",
        "feedbackSource": 0,
        "focusCommentID": None,
        "gridMediaWidth": None,
        "groupID": None,
        "scale": 1,
        "privacySelectorRenderLocation": "COMET_STREAM",
        "checkPhotosToReelsUpsellEligibility": False,
        "referringStoryRenderLocation": None,
        "renderLocation": "group",
        "useDefaultActor": False,
        "inviteShortLinkKey": None,
        "isFeed": False,
        "isFundraiser": False,
        "isFunFactPost": False,
        "isGroup": True,
        "isEvent": False,
        "isTimeline": False,
        "isSocialLearning": False,
        "isPageNewsFeed": False,
        "isProfileReviews": False,
        "isWorkSharedDraft": False,
        "__relay_internal__pv__CometUFIShareActionMigrationrelayprovider": True,
        "__relay_internal__pv__GHLShouldChangeSponsoredDataFieldNamerelayprovider": False,
        "__relay_internal__pv__GHLShouldChangeAdIdFieldNamerelayprovider": False,
        "__relay_internal__pv__CometUFI_dedicated_comment_routable_dialog_gkrelayprovider": True,
        "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
        "__relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider": False,
        "__relay_internal__pv__CometUFISingleLineUFIrelayprovider": True,
        "__relay_internal__pv__CometFeedStory_enable_reactor_facepilerelayprovider": False,
        "__relay_internal__pv__CometFeedStory_enable_social_bubblesrelayprovider": True,
        "__relay_internal__pv__CometFeedStory_enable_post_permalink_white_space_clickrelayprovider": False,
        "__relay_internal__pv__TestPilotShouldIncludeDemoAdUseCaserelayprovider": False,
        "__relay_internal__pv__FBReels_deprecate_short_form_video_context_gkrelayprovider": True,
        "__relay_internal__pv__FBReels_enable_view_dubbed_audio_type_gkrelayprovider": True,
        "__relay_internal__pv__CometFeedShareMedia_shouldPrefetchShareImagerelayprovider": False,
        "__relay_internal__pv__CometImmersivePhotoCanUserDisable3DMotionrelayprovider": False,
        "__relay_internal__pv__WorkCometIsEmployeeGKProviderrelayprovider": False,
        "__relay_internal__pv__IsMergQAPollsrelayprovider": False,
        "__relay_internal__pv__FBReelsMediaFooter_comet_enable_reels_ads_gkrelayprovider": True,
        "__relay_internal__pv__relay_provider_comet_ufi_ssr_seo_deferrelayprovider": True,
        "__relay_internal__pv__ReelsIFUCard_reelsIFULikeCountrelayprovider": False,
        "__relay_internal__pv__FBReelsIFUTileContent_reelsIFUPlayOnHoverrelayprovider": True,
        "__relay_internal__pv__GroupsCometGYSJFeedItemHeightrelayprovider": 206,
        "__relay_internal__pv__ShouldEnableBakedInTextStoriesrelayprovider": False,
        "__relay_internal__pv__StoriesShouldIncludeFbNotesrelayprovider": True,
        "__relay_internal__pv__groups_comet_use_glvrelayprovider": False,
        "__relay_internal__pv__GHLShouldChangeSponsoredAuctionDistanceFieldNamerelayprovider": False,
        "__relay_internal__pv__GHLShouldUseSponsoredAuctionLabelFieldNameV1relayprovider": False,
        "__relay_internal__pv__GHLShouldUseSponsoredAuctionLabelFieldNameV2relayprovider": False,
    }

    payload = {
        "av": FB_USER_ID,
        "__user": FB_USER_ID,
        "__a": "1",
        "__req": str(random.randint(1, 50)),
        "__hs": "19861.HYP:comet_pkg.2.1.1.1.0",
        "__comet_req": "1",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "ComposerStoryCreateMutation",
        "variables": json.dumps(variables),
        "doc_id": "36949139048065438",
        "fb_dtsg": fb_dtsg,
        "lsd": lsd,
        "jazoest": "2" + str(random.randint(1000, 9999)),
        "dpr": "2",
    }

    return payload


def publish_post(session: requests.Session, post_text: str) -> bool:
    fb_dtsg, lsd = extract_fb_dtsg_and_lsd(session)

    if not fb_dtsg:
        log("❌ fb_dtsg не найден")
        return False

    payload = build_graphql_payload(post_text, fb_dtsg, lsd)

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
        "x-fb-friendly-name": "ComposerStoryCreateMutation",
    }

    if lsd:
        headers["x-fb-lsd"] = lsd

    log(f"📤 GraphQL: doc_id=36949139048065438")

    try:
        resp = session.post(
            "https://www.facebook.com/api/graphql/",
            data=payload,
            headers=headers,
            timeout=30,
        )

        body = resp.text
        if body.startswith("for (;;);"):
            body = body[9:]

        log(f"📥 HTTP {resp.status_code}")
        log(f"📄 Тело: {body[:1500]}")

        if resp.status_code != 200:
            log(f"❌ HTTP {resp.status_code}")
            return False

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            log("⚠️ Ответ не JSON")
            return False

        if "error" in data:
            err = data["error"]
            summary = data.get("errorSummary", "")
            desc = data.get("errorDescription", "")
            log(f"⚠️ Facebook error {err}: {summary} — {desc}")
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
            m = re.search(r'"post_id"\s*:\s*"(\d+)"', body)
            if m:
                post_id = m.group(1)

        if post_id:
            url = f"https://www.facebook.com/groups/{FB_GROUP_ID}/posts/{post_id}"
            log(f"🔗 Пост: {url}")
            return True

        if "story_create" in body:
            log("✅ Пост создан (story_create)")
            return True

        log("⚠️ Неизвестный ответ, проверьте тело")
        return False

    except Exception as e:
        log(f"❌ Исключение: {e}")
        return False


def main():
    log("=" * 70)
    log("📘 FACEBOOK GROUP POSTER v3 (GraphQL + lsd)")
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
        log("⚙️ DRY_RUN: пропускаем отправку")
        return 0

    # 4. Загружаем куки и создаём сессию
    cookies_list = load_cookies()
    if not cookies_list:
        return 1

    session = requests.Session()
    for cookie in cookies_list:
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        domain = cookie.get("domain", ".facebook.com")
        session.cookies.set(name, value, domain=domain)

    log("🌐 Инициализация сессии...")
    try:
        resp = session.get("https://www.facebook.com/", timeout=15)
        log(f"✅ Facebook: HTTP {resp.status_code}")
    except Exception as e:
        log(f"❌ Не удалось загрузить facebook.com: {e}")
        return 1

    # 5. Публикуем
    log("\n🚀 Публикация...")
    success = publish_post(session, post_text)

    if success:
        log("\n✅ Пост успешно опубликован!")
        return 0
    else:
        log("\n❌ Не удалось опубликовать пост")
        return 1


if __name__ == "__main__":
    sys.exit(main())
