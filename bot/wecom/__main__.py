"""企业微信智能机器人入口：python -m bot.wecom"""

from __future__ import annotations

import asyncio
import logging
import re
import signal
from typing import Any

from bot.config import settings
from bot.logging_config import setup_logging
from bot.wecom.client import WecomBotClient
from bot.wecom.llm import chat_with_tools

logger = logging.getLogger(__name__)


def _extract_user_text(frame: dict[str, Any]) -> str:
    """从 aibot_msg_callback 帧里取出文本内容，去除 @机器人 前缀."""
    body = frame.get("body") or {}
    msgtype = body.get("msgtype")
    if msgtype != "text":
        return ""
    text = (body.get("text") or {}).get("content", "")
    # 群聊 @机器人 时 content 形如 "@机器人名 你好"，去掉 @xxx 前缀
    return re.sub(r"^@\S+\s*", "", text).strip()


async def main_async() -> None:
    setup_logging(settings.log_level, settings.log_format)

    if not settings.wecom_bot_id or not settings.wecom_bot_secret:
        logger.error("缺少 WECOM_BOT_ID / WECOM_BOT_SECRET，wecom-agent 无法启动")
        return

    client: WecomBotClient | None = None

    async def on_message(frame: dict[str, Any]) -> None:
        body = frame.get("body") or {}
        chat_type = body.get("chattype", "single")
        sender = (body.get("from") or {}).get("userid", "")
        text = _extract_user_text(frame)

        logger.info("[wecom] msg from=%s chat=%s text=%r", sender, chat_type, text[:80])
        if not text:
            return  # 非文本消息忽略

        try:
            reply = await chat_with_tools(text)
        except Exception as exc:
            logger.exception("LLM dispatch failed")
            reply = f"❌ 处理消息时出错：{exc}"

        if client is not None:
            try:
                await client.reply_text(frame, reply)
            except Exception:
                logger.exception("回复消息失败")

    async def on_event(frame: dict[str, Any]) -> None:
        body = frame.get("body") or {}
        event_type = body.get("event_type") or body.get("eventtype") or ""
        logger.info("[wecom] event=%s", event_type)
        # 进入会话事件 → 发欢迎语
        if client is not None and event_type in {"enter_chat", "enter", "subscribe"}:
            try:
                await client.reply_welcome(
                    frame,
                    f"您好，我是 {settings.wecom_bot_name}。可以问我：\n"
                    "  • 莫斯科现货库存\n"
                    "  • 今天的机器人日报",
                )
            except Exception:
                logger.exception("发送欢迎语失败")

    client = WecomBotClient(
        bot_id=settings.wecom_bot_id,
        secret=settings.wecom_bot_secret,
        ws_url=settings.wecom_ws_url,
        on_message=on_message,
        on_event=on_event,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("收到退出信号，准备关闭…")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows 下可能不支持

    runner = asyncio.create_task(client.run_forever())
    waiter = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait({runner, waiter}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await client.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
