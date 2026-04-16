"""通知服务 — 消息转发、客服通知等."""

from __future__ import annotations

import logging

from aiogram import Bot

from bot.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务.

    负责将消息转发到客服群组、通知管理员等。

    TODO: M4/M6 — 完善实现
    """

    def __init__(self, bot: Bot | None = None) -> None:
        self.bot = bot
        self.support_group_id = settings.support_group_id
        self.escalation_agent_id = settings.escalation_agent_id

    def set_bot(self, bot: Bot) -> None:
        """设置 Bot 实例（延迟绑定）."""
        self.bot = bot

    async def notify_support_group(
        self,
        text: str,
        user_id: int | None = None,
    ) -> int | None:
        """向普通客服群组发送通知.

        Returns:
            Telegram 消息 ID (用于后续追踪).
        """
        if not self.bot or not self.support_group_id:
            logger.warning("Bot 或 support_group_id 未设置，无法发送通知")
            return None

        msg = await self.bot.send_message(self.support_group_id, text)
        return msg.message_id

    async def notify_escalation_agent(
        self,
        text: str,
        user_id: int | None = None,
    ) -> int | None:
        """向特定人工客服发送通知.

        用于售后 AI 触发 5 次后的转接。
        """
        if not self.bot or not self.escalation_agent_id:
            logger.warning("Bot 或 escalation_agent_id 未设置，无法转接")
            return None

        msg = await self.bot.send_message(self.escalation_agent_id, text)
        return msg.message_id

    async def forward_to_support(
        self,
        chat_id: int,
        message_id: int,
    ) -> int | None:
        """将用户消息转发到客服群组."""
        if not self.bot or not self.support_group_id:
            return None

        msg = await self.bot.forward_message(
            chat_id=self.support_group_id,
            from_chat_id=chat_id,
            message_id=message_id,
        )
        return msg.message_id


# 全局服务实例
notification_service = NotificationService()
