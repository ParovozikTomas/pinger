# GitHub Site Pinger → Telegram

Скрипт по расписанию **GitHub Actions**:

1. обрабатывает команды из Telegram;
2. сохраняет URL и список пользователей в `data/` (коммит обратно в репо);
3. пингует все URL и шлёт отчёт админу и разрешённым пользователям.

> Команды выполняются **при следующем запуске** workflow (cron каждые 5 минут или вручную).

Репозиторий: https://github.com/ParovozikTomas/pinger

---

## Роли

| Роль | Кто | Права |
|------|-----|--------|
| **Админ** | `TELEGRAM_CHAT_ID` (секрет) | URL + `/allow` `/deny` `/users` |
| **Пользователь** | добавлен через `/allow` | `/add` `/del` `/list` |
| Остальные | — | только `/whoami` / сообщение «нет доступа» |

Список URL **общий** для всех. Отчёты пинга приходят админу и всем из `/allow`.

---

## Команды

### Для всех разрешённых

| Команда | Действие |
|---------|----------|
| `/help` | справка |
| `/list` | список URL |
| `/add https://example.com` | добавить URL |
| `/del 1` | удалить URL |
| `/whoami` | показать свой Telegram ID |

### Только админ

| Команда | Действие |
|---------|----------|
| `/users` | список разрешённых |
| `/allow 123456789` | выдать доступ |
| `/deny 1` или `/deny 123456789` | забрать доступ |

### Как добавить человека

1. Человек пишет боту `/whoami` → получает свой ID.  
2. Присылает ID вам.  
3. Вы пишете: `/allow 123456789`  
4. Дождитесь следующего run Actions (или **Run workflow**).  
5. Человек может пользоваться `/add`, `/list`, `/del`.

---

## Пошаговая настройка

### 1. Telegram-бот

1. [@BotFather](https://t.me/BotFather) → `/newbot` → токен.  
2. Напишите боту `/start`.  
3. Узнайте свой ID: `https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id": ...}`  
   или после деплоя — команда `/whoami`.

### 2. Secrets в GitHub

**Settings → Secrets and variables → Actions → New repository secret**

| Name | Secret |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | токен BotFather |
| `TELEGRAM_CHAT_ID` | **ваш** chat id (админ) |

### 3. Actions

1. Вкладка **Actions** → workflow **Site ping**  
2. **Run workflow** → ветка `master`

### 4. Проверка

1. `/add https://example.com` → Run workflow  
2. `/allow <id друга>` → Run workflow  
3. Друг: `/list`

---

## Расписание

В `.github/workflows/ping.yml`:

```yaml
- cron: "*/5 * * * *"
```

Минимум GitHub — каждые 5 минут (UTC).

---

## Файлы данных

```text
data/
  urls.json              # список сайтов
  allowed_users.json     # разрешённые пользователи
  telegram_offset.txt    # курсор Telegram updates
```
