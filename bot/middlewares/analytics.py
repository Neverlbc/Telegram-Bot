"""Analytics middleware."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.services.analytics import build_event_snapshot, record_event


class AnalyticsMiddleware(BaseMiddleware):
    """Record one sanitized analytics event per Telegram update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        snapshot = await build_event_snapshot(event, data)
        try:
            result = await handler(event, data)
        except Exception:
            if snapshot:
                event_data = dict(snapshot.get("event_data") or {})
                event_data["outcome"] = "error"
                snapshot["event_data"] = event_data
                await record_event(snapshot)
            raise

        if snapshot:
            event_data = dict(snapshot.get("event_data") or {})
            event_data["outcome"] = "ok"
            snapshot["event_data"] = event_data
            await record_event(snapshot)
        return result
