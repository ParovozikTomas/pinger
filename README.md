# GitHub Site Pinger → Telegram

Скрипт по расписанию **GitHub Actions**:

1. забирает команды из Telegram (`/add`, `/del`, `/list`);
2. сохраняет список URL в `data/urls.json` (коммитит обратно в репозиторий);
3. пингует все URL и шлёт отчёт в бота.

> **Важно:** Actions не держит бота онлайн 24/7. Команды обрабатываются **при следующем запуске workflow** (по cron или вручную). Сейчас cron — каждые 10 минут.

Репозиторий: https://github.com/ParovozikTomas/pinger

---

## Команды бота

| Команда | Действие |
|---------|----------|
| `/help` | справка |
| `/list` | показать URL |
| `/add https://example.com` | добавить |
| `/del 1` | удалить по номеру |
| `/del https://example.com` | удалить по URL |

Управлять может только чат из `TELEGRAM_CHAT_ID`.

---

## Пошаговая настройка

### 1. Telegram-бот

1. [@BotFather](https://t.me/BotFather) → `/newbot` → скопируйте токен.
2. Напишите боту `/start`.
3. Откройте в браузере: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Найдите `"chat":{"id": 123456789}` — это ваш Chat ID.

### 2. Secrets в GitHub

1. Откройте репозиторий → **Settings**
2. Слева: **Secrets and variables → Actions**
3. **New repository secret** — создайте два секрета:

| Name | Secret |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `TELEGRAM_CHAT_ID` | ваш chat id (число) |

### 3. Включить Actions (если нужно)

1. Вкладка **Actions**
2. Если GitHub просит разрешить workflows — нажмите **I understand my workflows, go ahead and enable them**

### 4. Первый запуск

1. **Actions** → слева workflow **Site ping**
2. **Run workflow** → **Run workflow** (ветка `master` или `main`)
3. Дождитесь завершения job

### 5. Проверка через бота

1. В Telegram: `/add https://example.com`
2. Снова **Actions → Site ping → Run workflow** (или подождите до 10 минут)
3. Бот ответит про добавление и пришлёт отчёт пинга
4. `/list`, `/del 1` — снова Run workflow / cron

---

## Расписание

Файл: `.github/workflows/ping.yml`

```yaml
- cron: "*/10 * * * *"
```

Время в **UTC**. Примеры:

- `0 * * * *` — каждый час  
- `*/15 * * * *` — каждые 15 минут  
- `0 6 * * *` — каждый день в 06:00 UTC  

После смены cron сделайте commit/push в репозиторий.

---

## Локальный запуск

```powershell
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="123456789"
python ping.py
```

Список URL читается/пишется в папку `data/`.

---

## Частые проблемы

| Проблема | Что проверить |
|----------|----------------|
| Бот молчит на `/add` | Запустите workflow вручную или дождитесь cron |
| Workflow не стартует по schedule | На GitHub free cron может задерживаться; первый раз запустите вручную |
| `TELEGRAM_BOT_TOKEN is not set` | Secrets добавлены с точными именами |
| Push из Actions падает | У workflow есть `permissions: contents: write` (уже в файле) |

---

## Файлы

```text
.
├── ping.py
├── data/
│   ├── urls.json
│   └── telegram_offset.txt
├── .github/workflows/ping.yml
├── .gitignore
└── README.md
```
