"""growth_engine.telegram — outbound Telegram alerts, config-driven.

Reads 05_System_Configs/notifications.json for chat_id + which .env file
holds the bot token (do not hardcode either here — this file is the delivery
mechanism, not the config). Fails loud if the token is missing: a HOT lead
alert that silently no-ops is worse than one that crashes with a clear reason,
since a silent failure here means the operator never finds out a HOT lead
existed.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from dotenv import dotenv_values

from paths import WORKSPACE as HQ_ROOT
NOTIFICATIONS_CONFIG = HQ_ROOT / "05_System_Configs" / "notifications.json"


class TelegramConfigError(RuntimeError):
    """Raised when Telegram delivery can't proceed — missing config or token."""


def _load_config() -> dict:
    if not NOTIFICATIONS_CONFIG.exists():
        raise TelegramConfigError(f"No notifications config at {NOTIFICATIONS_CONFIG}")
    config = json.loads(NOTIFICATIONS_CONFIG.read_text(encoding="utf-8"))
    telegram = config.get("telegram")
    if not telegram or not telegram.get("enabled", False):
        raise TelegramConfigError("Telegram delivery is disabled or unconfigured in notifications.json")
    return telegram


def send_message(text: str) -> None:
    """Sends one Telegram message using the chat_id + bot token resolved from
    notifications.json. Raises TelegramConfigError (config problem) or
    requests.RequestException (API/network problem) — caller decides how to
    surface it. Never returns a fake success."""
    telegram = _load_config()
    chat_id = telegram["chat_id"]
    token_key = telegram["bot_token_env"]

    # notifications.json is lower-trust than this file (it's config data, not
    # code) — same unvalidated-join risk as tenant.py had before that fix.
    # Requires prior write access to 05_System_Configs/ to matter in
    # practice, but closing it for consistency rather than leaving a second
    # instance of the same pattern unfixed.
    env_file = (HQ_ROOT / telegram["env_file"]).resolve()
    if HQ_ROOT.resolve() not in env_file.parents and env_file != HQ_ROOT.resolve():
        raise TelegramConfigError(
            f"Configured env_file '{telegram['env_file']}' resolves outside "
            f"{HQ_ROOT} — refusing."
        )
    if not env_file.exists():
        raise TelegramConfigError(f"Configured env_file does not exist: {env_file}")

    env_values = dotenv_values(env_file)
    token = env_values.get(token_key)
    if not token:
        raise TelegramConfigError(
            f"{token_key} is empty in {env_file}. Create a bot via @BotFather on "
            "Telegram, then paste the token into that file — this is the only "
            "missing piece for outbound delivery."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        # Every requests exception (HTTPError, ConnectionError, Timeout)
        # stringifies to something that includes the full request URL — and
        # the live bot token is embedded in that URL's path. Left unscrubbed,
        # a failed send prints/logs/gets-written-to-STATE.md with the token
        # in plaintext (this is exactly what happened before this fix — a
        # bad token or transient API error would commit the real token into
        # domain/lead-qualify/STATE.md, which is deliberately git-tracked).
        # Re-raise with the token/URL stripped out entirely.
        status = getattr(getattr(e, "response", None), "status_code", "no response")
        raise TelegramConfigError(
            f"Telegram API call failed (status: {status}). Token and full "
            "request URL deliberately omitted from this message — check the "
            "bot token and chat_id in your config."
        ) from e