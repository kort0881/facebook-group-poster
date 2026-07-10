#!/usr/bin/env python3
"""
Функции загрузки и обработки VPN-ключей.
Скопированы из proxy-auto-checker/post_to_telegram.py
"""
import os
import urllib.parse
from datetime import datetime

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FOLDER = os.path.join(WORK_DIR, "results")
PREMIUM_FOLDER = os.path.join(RESULTS_FOLDER, "premium")
LIGHT_VERIFIED = os.path.join(WORK_DIR, "checked", "latest", "verified.txt")


def clean_key(k: str) -> str:
    k = k.strip()
    if " " in k:
        k = k.split(" ")[0]
    return k


def fix_universal(key: str) -> str:
    key = key.strip()
    if not key.startswith("vless://") or "type=xhttp" not in key:
        return key
    try:
        parsed = urllib.parse.urlparse(key)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("type", [""])[0].lower() == "xhttp":
            query["type"] = ["http"]
        new_query = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment,
        ))
    except Exception:
        return key


def load_premium_keys():
    all_keys = []
    stats = {"elite": 0, "premium": 0, "good": 0}
    priority_files = [
        ("elite.txt", "elite"),
        ("premium.txt", "premium"),
        ("good.txt", "good"),
    ]
    for filename, category in priority_files:
        filepath = os.path.join(PREMIUM_FOLDER, filename)
        if not os.path.exists(filepath):
            print(f"  ⚠️ {filename} не найден")
            continue
        count = 0
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key = fix_universal(clean_key(line))
                    if key:
                        all_keys.append(key)
                        count += 1
        stats[category] = count
        print(f"  ✅ {filename}: {count} ключей")
    return all_keys, stats


def load_fallback_keys():
    verified_files = [
        f for f in os.listdir(RESULTS_FOLDER)
        if f.startswith("verified_") and f.endswith(".txt")
    ]
    semi_dead_files = [
        f for f in os.listdir(RESULTS_FOLDER)
        if f.startswith("semi_dead_") and f.endswith(".txt")
    ]
    if verified_files:
        latest = max(
            verified_files,
            key=lambda f: os.path.getmtime(os.path.join(RESULTS_FOLDER, f)),
        )
        source = "verified"
    elif semi_dead_files:
        latest = max(
            semi_dead_files,
            key=lambda f: os.path.getmtime(os.path.join(RESULTS_FOLDER, f)),
        )
        source = "semi_dead"
    else:
        return [], None, None
    filepath = os.path.join(RESULTS_FOLDER, latest)
    keys = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key = fix_universal(clean_key(line))
                if key:
                    keys.append(key)
    return keys, latest, source


def load_light_verified_keys():
    if not os.path.exists(LIGHT_VERIFIED):
        return []
    keys = []
    with open(LIGHT_VERIFIED, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key = fix_universal(clean_key(line))
                if key:
                    keys.append(key)
    return keys


def create_public_file(all_keys, stats=None):
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(RESULTS_FOLDER, exist_ok=True)
    filename = f"public_top200_{date_str}.txt"
    filepath = os.path.join(RESULTS_FOLDER, filename)
    top_keys = all_keys[:200]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Channel: @vlesstrojan\n")
        f.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write("# Verified: Triple-check (TCP + XRAY + Categories)\n")
        f.write(f"# Total: {len(top_keys)}\n\n")
        for key in top_keys:
            f.write(key + "\n")
    return filepath, len(top_keys)
