# GitLab Site Pinger → Telegram

Скрипт по расписанию GitLab CI пингует сайт и отправляет отчёт (HTTP-код и время ответа) в Telegram-бота.

## Что понадобится

- Репозиторий на GitLab (gitlab.com или свой инстанс)
- URL сайта для проверки
- Telegram-бот и chat ID, куда слать сообщения

---

## Пошаговая настройка

### 1. Создайте Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте `/newbot` и следуйте инструкциям (имя и username бота).
3. Скопируйте **токен** вида `123456:ABC-DEF...` — это `TELEGRAM_BOT_TOKEN`.

### 2. Узнайте Chat ID

**Личный чат с ботом**

1. Напишите боту любое сообщение (например `/start`).
2. Откройте в браузере (подставьте свой токен):

   ```text
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

3. В ответе найдите `"chat":{"id": 123456789}` — это `TELEGRAM_CHAT_ID`.

**Группа / канал**

1. Добавьте бота в группу (для канала — сделайте бота администратором с правом писать сообщения).
2. Напишите в группе любое сообщение (или перешлите пост в канал).
3. Снова откройте `getUpdates` — у группы/канала `id` обычно отрицательный, например `-1001234567890`.

### 3. Залейте проект в GitLab

1. Создайте новый проект в GitLab.
2. В корне репозитория должны быть файлы:

   - `ping.py` — скрипт пинга и отправки в Telegram  
   - `.gitlab-ci.yml` — job для CI  
   - `README.md` — эта инструкция  

3. Запушьте код:

   ```bash
   git init
   git add ping.py .gitlab-ci.yml README.md .gitignore
   git commit -m "Add scheduled site ping with Telegram reports"
   git remote add origin <URL_ВАШЕГО_РЕПО>
   git push -u origin main
   ```

### 4. Добавьте CI/CD Variables

В GitLab: **Settings → CI/CD → Variables → Add variable**.

| Variable              | Значение                         | Protected | Masked | Описание                          |
|-----------------------|----------------------------------|-----------|--------|-----------------------------------|
| `PING_URL`            | `https://example.com`            | по желанию| нет    | URL сайта для проверки            |
| `TELEGRAM_BOT_TOKEN`  | токен от BotFather               | да*       | **да** | Токен бота                        |
| `TELEGRAM_CHAT_ID`    | `123456789` или `-100...`        | да*       | нет**  | Куда слать сообщения              |

\* Если переменная **Protected**, schedule должен запускаться с **protected** ветки (обычно `main`/`master`).  
\*\* Masked работает только для значений, похожих на секреты (длинные строки без пробелов); chat ID часто нельзя замаскировать — это нормально.

Опционально:

| Variable              | Значение по умолчанию | Описание |
|-----------------------|-----------------------|----------|
| `PING_TIMEOUT`        | `15`                  | Таймаут HTTP-запроса (сек) |
| `NOTIFY_ONLY_ON_FAIL` | `false`               | `true` — писать в Telegram только при ошибке |

### 5. Создайте Pipeline Schedule

1. Откройте **Build → Pipeline schedules** (или **CI/CD → Schedules**).
2. Нажмите **New schedule**.
3. Заполните:

   - **Description**: например `Hourly site ping`
   - **Interval Pattern**: cron, например:
     - `0 * * * *` — каждый час  
     - `*/15 * * * *` — каждые 15 минут  
     - `0 9 * * *` — каждый день в 09:00 (UTC!)  
   - **Cron Timezone**: выберите нужный (или учтите, что по умолчанию часто UTC)
   - **Target branch**: `main` (или ваша основная ветка)
   - **Activated**: включено  

4. Сохраните schedule.

> Job `ping_site` в `.gitlab-ci.yml` запускается только для `schedule` (и вручную из Web UI). Обычный push в репозиторий пинг не триггерит.

### 6. Проверьте работу

1. В списке schedules нажмите **Play** (▶) у вашего расписания — сразу запустится pipeline.
2. Откройте pipeline → job `ping_site` → смотрите лог.
3. В Telegram должно прийти сообщение вида:

   ```text
   ✅ Site ping report
   URL: https://example.com
   Status: 200
   Time: 312 ms
   ```

При недоступности сайта:

```text
❌ Site ping report
URL: https://example.com
Status: N/A
Time: 15002 ms
Error: <timed out>
```

---

## Локальный запуск (для отладки)

```bash
export PING_URL="https://example.com"
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
python ping.py
```

На Windows (PowerShell):

```powershell
$env:PING_URL="https://example.com"
$env:TELEGRAM_BOT_TOKEN="123456:ABC..."
$env:TELEGRAM_CHAT_ID="123456789"
python ping.py
```

---

## Как это устроено

1. GitLab по cron запускает pipeline.
2. Job поднимает образ `python:3.12-alpine` и выполняет `python ping.py`.
3. Скрипт делает GET на `PING_URL`, замеряет время и HTTP-код.
4. Результат уходит в Telegram через Bot API (`sendMessage`).
5. При ошибке сайта job в GitLab будет красным (`allow_failure: true`, чтобы schedule не «ломал» видимость других процессов).

---

## Частые проблемы

| Проблема | Что проверить |
|----------|----------------|
| Сообщение не приходит | Написали ли боту `/start`; верный `TELEGRAM_CHAT_ID`; токен не с пробелами |
| Job skipped | Schedule активирован; ветка совпадает; source = `schedule` |
| `environment variable ... is not set` | Variables добавлены в проекте; для Protected — ветка protected |
| Сайт «упал», а код 403/401 | Нормально: пингер смотрит на HTTP-статус, не на «логин»; при необходимости смените URL на публичный health-check |
| Время срабатывания «не то» | Cron в GitLab часто в UTC — проверьте timezone у schedule |

---

## Файлы

```text
.
├── ping.py           # пинг + отправка в Telegram
├── .gitlab-ci.yml    # job по расписанию
├── .gitignore
└── README.md
```
