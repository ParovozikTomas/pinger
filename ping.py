#!/usr/bin/env python3
"""Scheduled site pinger with Telegram URL management (GitLab CI).

Commands are processed when the pipeline runs (schedule). The URL list is
stored in GitLab CI/CD variable PING_URLS (JSON array).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


HELP_TEXT = """\
Команды пингера:
/list — список URL
/add <url> — добавить URL
/del <номер|url> — удалить URL
/help — эта справка

Отчёт по всем URL приходит по расписанию GitLab.
Команды обрабатываются при следующем запуске pipeline.
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
    hdrs = {"User-Agent": "gitlab-site-pinger/2.0", **(headers or {})}
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


class GitlabVars:
    def __init__(self, api_url: str, project_id: str, token: str) -> None:
        self.base = (
            f"{api_url.rstrip('/')}/projects/"
            f"{urllib.parse.quote(str(project_id), safe='')}/variables"
        )
        self.headers = {"PRIVATE-TOKEN": token}

    def get(self, key: str, default: str | None = None) -> str | None:
        try:
            data = http_json("GET", f"{self.base}/{key}", headers=self.headers)
            return data.get("value", default)
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                return default
            raise

    def set(self, key: str, value: str) -> None:
        payload = {"value": value}
        encoded_key = urllib.parse.quote(key, safe="")
        try:
            http_json(
                "PUT",
                f"{self.base}/{encoded_key}",
                headers=self.headers,
                data=payload,
            )
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
            http_json(
                "POST",
                self.base,
                headers=self.headers,
                data={"key": key, "value": value},
            )


def parse_urls(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(u).strip() for u in data if str(u).strip()]
        if isinstance(data, str) and data.strip():
            return [data.strip()]
    except json.JSONDecodeError:
        pass
    parts = []
    for chunk in raw.replace(",", "\n").splitlines():
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url
    return url


def format_list(urls: list[str]) -> str:
    if not urls:
        return "Список URL пуст.\nДобавьте: /add https://example.com"
    lines = ["Список URL:"]
    for i, url in enumerate(urls, start=1):
        lines.append(f"{i}. {url}")
    return "\n".join(lines)


def handle_command(text: str, urls: list[str]) -> tuple[list[str], str]:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].split("@", 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in {"/start", "/help"}:
        return urls, HELP_TEXT

    if cmd == "/list":
        return urls, format_list(urls)

    if cmd == "/add":
        if not arg:
            return urls, "Использование: /add https://example.com"
        url = normalize_url(arg)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return urls, "Некорректный URL. Пример: /add https://example.com"
        if url in urls:
            return urls, f"Уже в списке:\n{url}"
        urls = [*urls, url]
        return urls, f"Добавлено:\n{url}\n\n{format_list(urls)}"

    if cmd in {"/del", "/delete", "/rm", "/remove"}:
        if not arg:
            return urls, "Использование: /del <номер> или /del <url>"
        if arg.isdigit():
            idx = int(arg)
            if idx < 1 or idx > len(urls):
                return urls, f"Нет пункта #{idx}.\n\n{format_list(urls)}"
            removed = urls[idx - 1]
            urls = [u for i, u in enumerate(urls, start=1) if i != idx]
            return urls, f"Удалено:\n{removed}\n\n{format_list(urls)}"
        url = normalize_url(arg)
        if url not in urls:
            return urls, f"URL не найден:\n{url}\n\n{format_list(urls)}"
        urls = [u for u in urls if u != url]
        return urls, f"Удалено:\n{url}\n\n{format_list(urls)}"

    return urls, "Неизвестная команда.\n\n" + HELP_TEXT


def process_telegram_commands(
    token: str,
    allowed_chat_id: str,
    urls: list[str],
    offset: int,
) -> tuple[list[str], int, bool]:
    before = list(urls)
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
        chat_id = str((message.get("chat") or {}).get("id", ""))
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        if chat_id != str(allowed_chat_id):
            print(f"Ignoring command from unauthorized chat {chat_id}")
            continue

        urls, reply = handle_command(text, urls)
        send_telegram(token, chat_id, reply)
        print(f"Handled command from {chat_id}: {text}")

    return urls, new_offset, urls != before


def ping(url: str, timeout: float) -> tuple[int | None, float, str | None]:
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "gitlab-site-pinger/2.0"},
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


def main() -> int:
    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")
    timeout = float(env("PING_TIMEOUT", "15") or "15")
    only_on_fail = (env("NOTIFY_ONLY_ON_FAIL", "false") or "").lower() in {
        "1",
        "true",
        "yes",
    }

    api_url = env("CI_API_V4_URL", "https://gitlab.com/api/v4") or "https://gitlab.com/api/v4"
    project_id = env("CI_PROJECT_ID")
    gitlab_token = env("GITLAB_API_TOKEN")

    store: GitlabVars | None = None
    if project_id and gitlab_token:
        store = GitlabVars(api_url, project_id, gitlab_token)
    else:
        print(
            "WARNING: GITLAB_API_TOKEN or CI_PROJECT_ID missing — "
            "URL changes from Telegram will not persist between runs",
            file=sys.stderr,
        )

    raw_urls = store.get("PING_URLS") if store else None
    raw_offset = store.get("TELEGRAM_OFFSET", "0") if store else None
    if raw_urls is None:
        raw_urls = env("PING_URLS")
    if not raw_urls:
        legacy = env("PING_URL")
        raw_urls = json.dumps([legacy]) if legacy else "[]"
    if raw_offset is None:
        raw_offset = env("TELEGRAM_OFFSET", "0") or "0"

    urls = parse_urls(raw_urls)
    try:
        offset = int(raw_offset)
    except ValueError:
        offset = 0

    try:
        urls, offset, urls_changed = process_telegram_commands(
            token, chat_id, urls, offset
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR processing Telegram commands: {exc}", file=sys.stderr)
        urls_changed = False

    if store:
        try:
            store.set("TELEGRAM_OFFSET", str(offset))
            if urls_changed:
                store.set("PING_URLS", json.dumps(urls, ensure_ascii=False))
                print(f"Saved PING_URLS ({len(urls)} items)")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR saving GitLab variables: {exc}", file=sys.stderr)
            try:
                send_telegram(
                    token,
                    chat_id,
                    f"Не удалось сохранить список URL в GitLab:\n{exc}",
                )
            except Exception:  # noqa: BLE001
                pass
            return 1

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

    try:
        send_telegram(token, chat_id, message)
        print("Telegram report sent")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to send Telegram report: {exc}", file=sys.stderr)
        return 1

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
