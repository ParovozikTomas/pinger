#!/usr/bin/env python3
"""Ping a URL and send the HTTP status report to Telegram."""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: environment variable {name} is not set", file=sys.stderr)
        sys.exit(1)
    return value


def ping(url: str, timeout: float) -> tuple[int | None, float, str | None]:
    """Return (status_code, elapsed_ms, error_message)."""
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "gitlab-site-pinger/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return response.getcode(), elapsed_ms, None
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return exc.code, elapsed_ms, str(exc.reason)
    except Exception as exc:  # noqa: BLE001 — report any network failure to Telegram
        elapsed_ms = (time.perf_counter() - started) * 1000
        return None, elapsed_ms, str(exc)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.getcode() != 200:
            raise RuntimeError(f"Telegram API returned HTTP {response.getcode()}")


def build_message(
    url: str,
    status: int | None,
    elapsed_ms: float,
    error: str | None,
) -> tuple[str, bool]:
    ok = status is not None and 200 <= status < 400
    icon = "✅" if ok else "❌"
    lines = [
        f"{icon} Site ping report",
        f"URL: {url}",
        f"Status: {status if status is not None else 'N/A'}",
        f"Time: {elapsed_ms:.0f} ms",
    ]
    if error:
        lines.append(f"Error: {error}")
    return "\n".join(lines), ok


def main() -> int:
    url = require_env("PING_URL")
    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")
    timeout = float(os.environ.get("PING_TIMEOUT", "15"))
    only_on_fail = os.environ.get("NOTIFY_ONLY_ON_FAIL", "").lower() in {
        "1",
        "true",
        "yes",
    }

    status, elapsed_ms, error = ping(url, timeout)
    message, ok = build_message(url, status, elapsed_ms, error)

    print(message)

    if only_on_fail and ok:
        print("OK — skipping Telegram (NOTIFY_ONLY_ON_FAIL is enabled)")
        return 0

    try:
        send_telegram(token, chat_id, message)
        print("Telegram message sent")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to send Telegram message: {exc}", file=sys.stderr)
        return 1

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
