#!/usr/bin/env python3
"""Scheduled site pinger with Telegram URL + user management (GitHub Actions).

Admin (TELEGRAM_CHAT_ID) can allow/deny users. Allowed users manage the shared
URL list. Data is stored under data/ and committed by the workflow.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_HELP = """\
Команды:
/list — список URL
/add <url> — добавить URL
/del <номер|url> — удалить URL
/whoami — показать ваш Telegram ID
/help — справка

Команды обрабатываются при следующем запуске GitHub Actions.
"""

ADMIN_HELP = """\
Команды (админ):
/list — список URL
/add <url> — добавить URL
/del <номер|url> — удалить URL
/users — список разрешённых пользователей
/allow <id> — разрешить пользователю
/deny <номер|id> — забрать доступ
/whoami — ваш Telegram ID
/help — справка

Как добавить человека:
1) он пишет боту /whoami и присылает вам id
2) вы: /allow <id>

Команды обрабатываются при следующем запуске GitHub Actions.
"""


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        print(f"ERROR: environment variable {name} is not set", file=sys.stderr)
        sys.exit(1)
    return value


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | bytes | None = None,
    timeout: float = 30,
) -> Any:
    hdrs = {"User-Agent": "github-site-pinger/2.1", **(headers or {})}
    body: bytes | None = None
    if isinstance(data, dict):
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    elif isinstance(data, bytes):
        body = data

    request = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def telegram_api(token: str, method: str, params: dict[str, Any] | None = None) -> Any:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params is None:
        return http_json("GET", url)
    payload = urllib.parse.urlencode(
        {k: str(v) for k, v in params.items() if v is not None}
    ).encode("utf-8")
    return http_json(
        "POST",
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )


def send_telegram(token: str, chat_id: str, text: str) -> None:
    result = telegram_api(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )
    if not result or not result.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {result}")


def data_dir() -> Path:
    path = Path(env("DATA_DIR", "data") or "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json_list(filename: str) -> list[str]:
    path = data_dir() / filename
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    return []


def save_json_list(filename: str, items: list[str]) -> None:
    path = data_dir() / filename
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_urls() -> list[str]:
    urls = load_json_list("urls.json")
    if urls:
        return urls
    legacy = env("PING_URL")
    return [legacy] if legacy else []


def save_urls(urls: list[str]) -> None:
    save_json_list("urls.json", urls)


def load_allowed_users() -> list[str]:
    return load_json_list("allowed_users.json")


def save_allowed_users(users: list[str]) -> None:
    save_json_list("allowed_users.json", users)


def load_offset() -> int:
    path = data_dir() / "telegram_offset.txt"
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def save_offset(offset: int) -> None:
    path = data_dir() / "telegram_offset.txt"
    path.write_text(str(offset) + "\n", encoding="utf-8")


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url
    return url


def format_urls(urls: list[str]) -> str:
    if not urls:
        return "Список URL пуст.\nДобавьте: /add https://example.com"
    lines = ["Список URL:"]
    for i, url in enumerate(urls, start=1):
        lines.append(f"{i}. {url}")
    return "\n".join(lines)


def format_users(admin_id: str, users: list[str]) -> str:
    lines = [f"Админ: {admin_id}", "Разрешённые пользователи:"]
    if not users:
        lines.append("(пусто)")
        lines.append("Добавить: /allow <telegram_id>")
        return "\n".join(lines)
    for i, uid in enumerate(users, start=1):
        lines.append(f"{i}. {uid}")
    return "\n".join(lines)


def is_admin(actor_id: str, admin_id: str) -> bool:
    return str(actor_id) == str(admin_id)


def is_allowed(actor_id: str, admin_id: str, allowed: list[str]) -> bool:
    return is_admin(actor_id, admin_id) or str(actor_id) in {str(u) for u in allowed}


def handle_command(
    text: str,
    *,
    actor_id: str,
    admin_id: str,
    urls: list[str],
    allowed: list[str],
) -> tuple[list[str], list[str], str]:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].split("@", 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    admin = is_admin(actor_id, admin_id)

    if cmd == "/whoami":
        role = "админ" if admin else ("пользователь" if is_allowed(actor_id, admin_id, allowed) else "нет доступа")
        return urls, allowed, f"Ваш Telegram ID: {actor_id}\nСтатус: {role}"

    if cmd in {"/start", "/help"}:
        if not is_allowed(actor_id, admin_id, allowed):
            return (
                urls,
                allowed,
                "Нет доступа к боту.\n"
                f"Ваш ID: {actor_id}\n"
                f"Попросите админа выполнить:\n/allow {actor_id}",
            )
        return urls, allowed, ADMIN_HELP if admin else USER_HELP

    if not is_allowed(actor_id, admin_id, allowed):
        return (
            urls,
            allowed,
            "Нет доступа.\n"
            f"Ваш ID: {actor_id}\n"
            f"Попросите админа:\n/allow {actor_id}",
        )

    if cmd == "/list":
        return urls, allowed, format_urls(urls)

    if cmd == "/add":
        if not arg:
            return urls, allowed, "Использование: /add https://example.com"
        url = normalize_url(arg)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return urls, allowed, "Некорректный URL. Пример: /add https://example.com"
        if url in urls:
            return urls, allowed, f"Уже в списке:\n{url}"
        urls = [*urls, url]
        return urls, allowed, f"Добавлено:\n{url}\n\n{format_urls(urls)}"

    if cmd in {"/del", "/delete", "/rm", "/remove"}:
        if not arg:
            return urls, allowed, "Использование: /del <номер> или /del <url>"
        if arg.isdigit():
            idx = int(arg)
            if idx < 1 or idx > len(urls):
                return urls, allowed, f"Нет пункта #{idx}.\n\n{format_urls(urls)}"
            removed = urls[idx - 1]
            urls = [u for i, u in enumerate(urls, start=1) if i != idx]
            return urls, allowed, f"Удалено:\n{removed}\n\n{format_urls(urls)}"
        url = normalize_url(arg)
        if url not in urls:
            return urls, allowed, f"URL не найден:\n{url}\n\n{format_urls(urls)}"
        urls = [u for u in urls if u != url]
        return urls, allowed, f"Удалено:\n{url}\n\n{format_urls(urls)}"

    # Admin-only user management
    if cmd in {"/users", "/allow", "/deny", "/ban", "/unallow"}:
        if not admin:
            return urls, allowed, "Только админ может управлять пользователями."

        if cmd == "/users":
            return urls, allowed, format_users(admin_id, allowed)

        if cmd == "/allow":
            if not arg:
                return urls, allowed, "Использование: /allow <telegram_id>"
            uid = arg.strip()
            if not uid.lstrip("-").isdigit():
                return urls, allowed, "ID должен быть числом. Человек пишет боту /whoami"
            if uid == str(admin_id):
                return urls, allowed, "Это ID админа — доступ и так есть."
            if uid in allowed:
                return urls, allowed, f"Уже разрешён: {uid}\n\n{format_users(admin_id, allowed)}"
            allowed = [*allowed, uid]
            return urls, allowed, f"Разрешён доступ: {uid}\n\n{format_users(admin_id, allowed)}"

        # /deny /ban /unallow
        if not arg:
            return urls, allowed, "Использование: /deny <номер|telegram_id>"
        if arg.isdigit() and not arg.startswith("-"):
            # Prefer index if it matches a list position; numeric ids are usually long
            idx = int(arg)
            if 1 <= idx <= len(allowed) and len(arg) <= 3:
                removed = allowed[idx - 1]
                allowed = [u for i, u in enumerate(allowed, start=1) if i != idx]
                return (
                    urls,
                    allowed,
                    f"Доступ закрыт: {removed}\n\n{format_users(admin_id, allowed)}",
                )
        uid = arg.strip()
        if uid == str(admin_id):
            return urls, allowed, "Нельзя забрать доступ у админа."
        if uid not in allowed:
            return urls, allowed, f"ID не в списке: {uid}\n\n{format_users(admin_id, allowed)}"
        allowed = [u for u in allowed if u != uid]
        return urls, allowed, f"Доступ закрыт: {uid}\n\n{format_users(admin_id, allowed)}"

    return urls, allowed, "Неизвестная команда.\n\n" + (ADMIN_HELP if admin else USER_HELP)


def actor_id_from_message(message: dict[str, Any]) -> str:
    """Prefer private chat id; fall back to from.id."""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    if chat_type == "private" and chat_id is not None:
        return str(chat_id)
    from_user = message.get("from") or {}
    if from_user.get("id") is not None:
        return str(from_user["id"])
    return str(chat_id or "")


def process_telegram_commands(
    token: str,
    admin_id: str,
    urls: list[str],
    allowed: list[str],
    offset: int,
) -> tuple[list[str], list[str], int]:
    result = telegram_api(
        token,
        "getUpdates",
        {"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["message"])},
    )
    if not result or not result.get("ok"):
        raise RuntimeError(f"getUpdates failed: {result}")

    new_offset = offset
    for update in result.get("result") or []:
        update_id = int(update["update_id"])
        new_offset = max(new_offset, update_id + 1)

        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            continue

        actor_id = actor_id_from_message(message)
        reply_chat_id = str((message.get("chat") or {}).get("id") or actor_id)

        urls, allowed, reply = handle_command(
            text,
            actor_id=actor_id,
            admin_id=admin_id,
            urls=urls,
            allowed=allowed,
        )
        send_telegram(token, reply_chat_id, reply)
        print(f"Handled from {actor_id}: {text}")

    return urls, allowed, new_offset


def ping(url: str, timeout: float) -> tuple[int | None, float, str | None]:
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "github-site-pinger/2.1"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return response.getcode(), elapsed_ms, None
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return exc.code, elapsed_ms, str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        return None, elapsed_ms, str(exc)


def build_report(
    results: list[tuple[str, int | None, float, str | None]],
) -> tuple[str, bool]:
    if not results:
        return (
            "Список URL пуст — нечего пинговать.\nДобавьте: /add https://example.com",
            True,
        )

    all_ok = True
    lines = ["📊 Site ping report"]
    for url, status, elapsed_ms, error in results:
        ok = status is not None and 200 <= status < 400
        all_ok = all_ok and ok
        icon = "✅" if ok else "❌"
        lines.append(
            f"{icon} {url}\n"
            f"   Status: {status if status is not None else 'N/A'} · {elapsed_ms:.0f} ms"
        )
        if error:
            lines.append(f"   Error: {error}")
    return "\n".join(lines), all_ok


def report_recipients(admin_id: str, allowed: list[str]) -> list[str]:
    seen: set[str] = set()
    recipients: list[str] = []
    for uid in [admin_id, *allowed]:
        uid = str(uid)
        if uid not in seen:
            seen.add(uid)
            recipients.append(uid)
    return recipients


def main() -> int:
    token = require_env("TELEGRAM_BOT_TOKEN")
    admin_id = require_env("TELEGRAM_CHAT_ID")
    timeout = float(env("PING_TIMEOUT", "15") or "15")
    only_on_fail = (env("NOTIFY_ONLY_ON_FAIL", "false") or "").lower() in {
        "1",
        "true",
        "yes",
    }

    urls = load_urls()
    allowed = load_allowed_users()
    offset = load_offset()

    try:
        urls, allowed, offset = process_telegram_commands(
            token, admin_id, urls, allowed, offset
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR processing Telegram commands: {exc}", file=sys.stderr)

    save_urls(urls)
    save_allowed_users(allowed)
    save_offset(offset)
    print(
        f"Saved {len(urls)} URL(s), {len(allowed)} allowed user(s), offset={offset}"
    )

    results: list[tuple[str, int | None, float, str | None]] = []
    for url in urls:
        status, elapsed_ms, error = ping(url, timeout)
        results.append((url, status, elapsed_ms, error))
        print(f"{url} -> {status} ({elapsed_ms:.0f} ms) {error or ''}")

    message, all_ok = build_report(results)
    print(message)

    if only_on_fail and all_ok and urls:
        print("OK — skipping Telegram report (NOTIFY_ONLY_ON_FAIL)")
        return 0

    send_errors = 0
    for recipient in report_recipients(admin_id, allowed):
        try:
            send_telegram(token, recipient, message)
            print(f"Telegram report sent to {recipient}")
        except Exception as exc:  # noqa: BLE001
            send_errors += 1
            print(f"ERROR: failed to send to {recipient}: {exc}", file=sys.stderr)

    if send_errors:
        return 1
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
