# GitLab Site Pinger → Telegram

Скрипт по расписанию GitLab CI:

1. забирает команды из Telegram (`/add`, `/del`, `/list`);
2. сохраняет список URL в CI/CD Variable;
3. пингует все URL и шлёт отчёт в бота.

> **Важно:** GitLab CI не держит бота онлайн 24/7. Команды обрабатываются **при следующем запуске schedule**. Для удобства ставьте cron чаще, например каждые 10 минут (`*/10 * * * *`). Ответ бота придёт после этого запуска.

Мгновенные ответы без задержки нужны только если бот крутится на отдельном сервере (VPS / Railway и т.п.) — этот проект так не устроен.

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

1. [@BotFather](https://t.me/BotFather) → `/newbot` → скопируйте токен (`TELEGRAM_BOT_TOKEN`).
2. Напишите боту `/start`.
3. Откройте `https://api.telegram.org/bot<TOKEN>/getUpdates` и найдите `"chat":{"id": ...}` → это `TELEGRAM_CHAT_ID`.

### 2. Код в GitLab

Репозиторий: файлы `ping.py`, `.gitlab-ci.yml`, `README.md`.  
Ветка с schedule: `master` или `main`.

### 3. CI/CD Variables

**Settings → CI/CD → Variables → Add variable**

| Variable | Значение | Masked | Описание |
|----------|----------|--------|----------|
| `TELEGRAM_BOT_TOKEN` | токен BotFather | да | бот |
| `TELEGRAM_CHAT_ID` | ваш chat id | нет | кто управляет и куда отчёты |
| `GITLAB_API_TOKEN` | токен с правом писать CI variables | да | сохранение списка URL |
| `PING_URLS` | `[]` | нет | список URL (JSON), создайте вручную |
| `TELEGRAM_OFFSET` | `0` | нет | курсор Telegram updates |

`PING_URL` больше не обязателен — URL добавляются через бота.

#### Как создать `GITLAB_API_TOKEN`

Нужен токен, который может читать/менять **CI/CD Variables** проекта.

**Вариант A — Project Access Token** (удобнее):

1. Проект → **Settings → Access Tokens**
2. Name: `pinger-vars`
3. Role: **Maintainer** (или Developer, если хватает прав на variables)
4. Scopes: `api`
5. Create → скопируйте токен в `GITLAB_API_TOKEN`

**Вариант B — Personal Access Token** своего пользователя с scope `api` (или fine-grained правом на CI/CD variables проекта).

Если токена нет, `/add` и `/del` в логе сработают, но **список не сохранится** до следующего run.

### 4. Pipeline Schedule

1. **Build → Pipeline schedules → New schedule**
2. Cron, например `*/10 * * * *` (каждые 10 минут)
3. Timezone — ваш
4. Target branch — `master` / `main`
5. Activated — on

Чем чаще schedule, тем быстрее бот «отвечает» на `/add` и `/del`.

### 5. Проверка

1. Напишите боту: `/add https://example.com`
2. В schedules нажмите **Play** (или дождитесь cron)
3. Бот должен ответить, что URL добавлен, и прислать отчёт пинга
4. `/list`, затем `/del 1` — снова Play / cron

Пример отчёта:

```text
📊 Site ping report
✅ https://example.com
   Status: 200 · 312 ms
❌ https://down.example
   Status: N/A · 15002 ms
   Error: timed out
```

---

## Опциональные переменные

| Variable | По умолчанию | Описание |
|----------|--------------|----------|
| `PING_TIMEOUT` | `15` | таймаут HTTP (сек) |
| `NOTIFY_ONLY_ON_FAIL` | `false` | `true` — отчёт только если есть ошибки |

---

## Локальный запуск

Без `GITLAB_API_TOKEN` список из Telegram **не сохранится** между запусками. Для разового теста:

```powershell
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="123456789"
$env:PING_URLS='["https://example.com"]'
python ping.py
```

С сохранением в GitLab дополнительно:

```powershell
$env:CI_API_V4_URL="https://gitlab.com/api/v4"
$env:CI_PROJECT_ID="12345678"   # Settings → General → Project ID
$env:GITLAB_API_TOKEN="glpat-..."
python ping.py
```

---

## Как это устроено

1. Schedule запускает `ping.py`.
2. Скрипт читает `getUpdates` Telegram и выполняет команды от `TELEGRAM_CHAT_ID`.
3. Список URL пишется в variable `PING_URLS` через GitLab API.
4. Все URL пингуются, сводный отчёт уходит в тот же чат.

---

## Частые проблемы

| Проблема | Что проверить |
|----------|----------------|
| Бот молчит на `/add` | Дождитесь schedule или нажмите Play; cron слишком редкий |
| «Не удалось сохранить список» | `GITLAB_API_TOKEN` с `api`; роль Maintainer; variable не Protected на unprotected ветке |
| Команды из другого чата игнор | Управление только у `TELEGRAM_CHAT_ID` |
| Пустой отчёт | Список пуст — сначала `/add` |

---

## Файлы

```text
.
├── ping.py           # команды бота + пинг + отчёт
├── .gitlab-ci.yml    # job по расписанию
├── .gitignore
└── README.md
```
