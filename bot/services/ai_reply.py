"""AI 自动回复服务 — 骨架."""

from __future__ import annotations

import logging

from bot.config import settings

logger = logging.getLogger(__name__)


class AIReplyService:
    """AI 自动回复服务.

    未发货订单由 AI 生成拖延回复。
    同一用户对同一订单触发 5 次后自动转特定人工。
    触发计数存储在 Redis，key: ``ai_reply:{user_id}:{order_id}``

    TODO: M5a — 完善实现
    """

    def __init__(self) -> None:
        self.max_count = settings.ai_reply_max_count
        self.ttl_days = settings.ai_reply_ttl_days

    async def generate_reply(
        self,
        user_id: int,
        order_id: str,
        lang: str = "zh",
        days_waiting: int = 0,
    ) -> str:
        """生成 AI 拖延回复.

        Args:
            user_id: 用户 Telegram ID.
            order_id: 聚水潭订单号.
            lang: 用户语言.
            days_waiting: 已等待天数.

        Returns:
            AI 生成的回复文本.

        TODO: 实现 OpenAI / Claude API 调用
        """
        # 占位回复
        placeholders = {
            "zh": f"您的订单正在加紧处理中，预计 3-5 个工作日内发出，感谢您的耐心等待。",
            "en": "Your order is being processed. Expected to ship within 3-5 business days. Thank you for your patience.",
            "ru": "Ваш заказ обрабатывается. Ожидаемая отправка в течение 3-5 рабочих дней. Спасибо за ваше терпение.",
        }
        return placeholders.get(lang, placeholders["zh"])

    async def get_reply_count(self, user_id: int, order_id: str) -> int:
        """获取当前触发计数.

        TODO: 从 Redis 读取
        """
        return 0

    async def increment_count(self, user_id: int, order_id: str) -> int:
        """计数 +1 并返回新值.

        TODO: Redis INCR
        """
        return 1

    async def should_escalate(self, user_id: int, order_id: str) -> bool:
        """是否应该转人工."""
        count = await self.get_reply_count(user_id, order_id)
        return count >= self.max_count


# 全局服务实例
ai_reply_service = AIReplyService()
