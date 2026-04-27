"""Sanitized analytics event recording."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from bot.config import settings
from bot.keyboards.callbacks import (
    InventoryCallback,
    LangCallback,
    MenuCallback,
    NavCallback,
    ServiceCenterCallback,
    VipCallback,
)
from bot.models import async_session
from bot.models.analytics import AnalyticsEvent

logger = logging.getLogger(__name__)

MAX_FIELD_LEN = 128
MAX_EVENT_NAME_LEN = 96

CALLBACK_CLASSES = {
    "lang": LangCallback,
    "menu": MenuCallback,
    "nav": NavCallback,
    "inv": InventoryCallback,
    "sc": ServiceCenterCallback,
    "vip": VipCallback,
}

PREFIX_MODULES = {
    "lang": "language",
    "menu": "menu",
    "nav": "navigation",
    "inv": "inventory",
    "sc": "service_center",
    "vip": "vandych",
}

STATE_MODULES = {
    "InventoryStates": "inventory",
    "ServiceCenterStates": "service_center",
    "VipStates": "vandych",
}

SENSITIVE_CALLBACK_FIELDS = {"cdek_no", "order_id"}


def analytics_available() -> bool:
    """Return whether DB-backed analytics should run."""
    return bool(settings.mysql_password and settings.mysql_password != "your_password_here")


def _trim(value: Any, max_len: int = MAX_FIELD_LEN) -> str:
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _tg_user(event: TelegramObject) -> TgUser | None:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return None


def _message_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.message_id
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.message_id
    return None


def _chat_info(event: TelegramObject) -> tuple[int | None, str | None]:
    if isinstance(event, Message):
        return event.chat.id, event.chat.type
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat.id, event.message.chat.type
    return None, None


def _password_kind(text: str | None) -> str:
    password = (text or "").strip()
    if not password:
        return ""
    if password == settings.vip_inventory_password.strip():
        return "vip_inventory"
    if password == settings.service_admin_password.strip():
        return "service_admin"
    if password == settings.vandych_password.strip():
        return "vandych"
    return ""


def _module_from_state(state_name: str | None) -> str | None:
    if not state_name:
        return None
    prefix = state_name.split(":", 1)[0]
    return STATE_MODULES.get(prefix)


async def _state_name(data: dict[str, Any]) -> str | None:
    state: FSMContext | None = data.get("state")
    if not state:
        return None
    try:
        return await state.get_state()
    except Exception as exc:
        logger.debug("failed to read FSM state for analytics: %s", exc)
        return None


def _safe_callback_payload(callback_data: str) -> dict[str, Any]:
    prefix = callback_data.split(":", 1)[0] if callback_data else ""
    payload: dict[str, Any] = {"prefix": prefix}

    callback_cls = CALLBACK_CLASSES.get(prefix)
    if not callback_cls:
        return payload

    try:
        parsed = callback_cls.unpack(callback_data)
    except Exception:
        return payload

    if hasattr(parsed, "model_dump"):
        values = parsed.model_dump()
    else:
        values = parsed.dict()

    for key in SENSITIVE_CALLBACK_FIELDS:
        values.pop(key, None)
    payload.update(values)
    return payload


async def build_event_snapshot(event: TelegramObject, data: dict[str, Any]) -> dict[str, Any] | None:
    """Build an event payload before the handler mutates state."""
    tg_user = _tg_user(event)
    chat_id, chat_type = _chat_info(event)
    state_name = await _state_name(data)
    lang = data.get("lang")

    base: dict[str, Any] = {
        "telegram_id": tg_user.id if tg_user else None,
        "chat_id": chat_id,
        "chat_type": _trim(chat_type, 32) if chat_type else None,
        "message_id": _message_id(event),
        "language": _trim(lang, 8) if lang else None,
        "state": _trim(state_name, 128) if state_name else None,
    }

    if isinstance(event, CallbackQuery):
        callback_data = event.data or ""
        payload = _safe_callback_payload(callback_data)
        prefix = payload.get("prefix", "")
        module = PREFIX_MODULES.get(str(prefix), str(prefix) or "callback")
        action = payload.get("action") or payload.get("code") or "unknown"
        action_text = _trim(action, 64)
        return {
            **base,
            "event_type": "callback",
            "event_name": _trim(f"{module}.{action_text}", MAX_EVENT_NAME_LEN),
            "module": _trim(module, 64),
            "action": action_text,
            "event_data": payload,
        }

    if isinstance(event, Message):
        text = event.text or ""
        password_kind = _password_kind(text)
        if password_kind:
            module = "hidden_access"
            action = password_kind
            event_name = "hidden_access.password_success"
            event_data = {"kind": password_kind}
        elif text.startswith("/"):
            command = text.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/") or "unknown"
            module = "command"
            action = _trim(command, 64)
            event_name = f"command.{action}"
            event_data = {"command": action}
        else:
            module = _module_from_state(state_name) or "message"
            action = "text_input" if state_name else "text_message"
            event_name = f"{module}.{action}"
            event_data = {"has_text": bool(text), "content_type": event.content_type}

        return {
            **base,
            "event_type": "message",
            "event_name": _trim(event_name, MAX_EVENT_NAME_LEN),
            "module": _trim(module, 64),
            "action": _trim(action, 64),
            "event_data": event_data,
        }

    return None


async def record_event(snapshot: dict[str, Any] | None) -> None:
    """Persist an analytics event in an isolated DB transaction."""
    if not snapshot or not analytics_available():
        return

    try:
        async with async_session() as session:
            session.add(AnalyticsEvent(**snapshot))
            await session.commit()
    except Exception as exc:
        logger.warning("analytics event write failed: %s", exc)
