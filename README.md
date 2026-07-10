# Facebook Group Poster

Автоматическая публикация VPN-ключей в Facebook Group.

## Описание

Скрипт загружает проверенные ключи из `proxy-auto-checker` (репозиторий [kort0881/proxy-auto-checker](https://github.com/kort0881/proxy-auto-checker)), формирует пост и публикует его в Facebook Group через Selenium + undetected-chromedriver.

## Структура

```
facebook-group-poster/
├── post_to_facebook.py       # Основной скрипт публикации
├── key_loader.py             # Функции загрузки ключей (из proxy-auto-checker)
├── requirements.txt          # Зависимости
├── .github/workflows/
│   └── facebook-poster.yml   # GitHub Actions (каждые 6 часов)
├── .gitignore
└── README.md
```

## Как работает

1. GitHub Actions чекаутит `proxy-auto-checker` (ключи) и `facebook-group-poster` (скрипт)
2. Копирует папки `results/` и `checked/`, а также `cover_public.jpg`
3. Запускает `post_to_facebook.py` с headless Chrome
4. Скрипт загружает куки из `FACEBOOK_COOKIES_B64`, открывает группу, вставляет текст + фото + файл с ключами и публикует

## Переменные окружения (секреты)

| Переменная | Описание |
|---|---|
| `FACEBOOK_COOKIES_B64` | Base64-строка JSON с куками Facebook (обязательно) |
| `FB_GROUP_ID` | ID группы (по умолчанию: 2478873955927710) |
| `FB_DRY_RUN` | `1` — тестовый прогон без публикации |

## Обновление кук

Куки Facebook живут ~30-60 дней. Чтобы обновить:

1. Открой Facebook в браузере
2. Открой консоль (F12 → Console)
3. Вставь:
```js
copy(JSON.stringify(document.cookie.split(';').reduce((cookies, cookie) => {
    const [name, value] = cookie.trim().split('=');
    cookies[name] = decodeURIComponent(value);
    return cookies;
}, {})));
```
4. Закодируй полученный JSON в Base64:
```bash
echo -n '{"cookie":"value",...}' | base64 -w0
```
5. Обнови секрет `FACEBOOK_COOKIES_B64` в Settings → Secrets and variables → Actions

## Расписание

По умолчанию — каждые 6 часов (`0 */6 * * *`). Можно запустить вручную через `workflow_dispatch`.
