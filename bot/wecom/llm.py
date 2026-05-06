"""DeepSeek tool-calling — 把用户消息丢给 LLM，让它决定调哪个工具，再回写最终回复。

最多 3 轮工具调用循环（防止死循环）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from bot.config import settings
from bot.wecom.tools import TOOL_HANDLERS, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是 {bot_name}，A-BF 跨境电商团队的内部助理。你的工作是：\n"
    "1) 当用户问及莫斯科现货库存时，调用 get_inventory；\n"
    "2) 当用户问及 Telegram Bot 的日报、今日数据、统计时，调用 get_daily_report；\n"
    "3) 其他闲聊问题简短礼貌回应，避免无关长篇大论；\n"
    "回复用中文，简洁直接，不要多余前缀。"
)

MAX_TOOL_LOOPS = 3


async def chat_with_tools(user_text: str) -> str:
    """主入口：发送一条用户消息给 DeepSeek，处理工具调用，返回最终文本回复。"""
    if not settings.deepseek_api_key:
        return "⚠️ DeepSeek API Key 未配置，无法处理智能问答。"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(bot_name=settings.wecom_bot_name)},
        {"role": "user", "content": user_text},
    ]

    for loop in range(MAX_TOOL_LOOPS):
        try:
            response = await _call_deepseek(messages)
        except Exception as exc:
            logger.exception("DeepSeek call failed")
            return f"❌ 调用 LLM 失败：{exc}"

        if not response:
            return "❌ LLM 没有返回内容。"

        message = response.get("choices", [{}])[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            content = (message.get("content") or "").strip()
            return content or "（LLM 返回为空）"

        # 把 LLM 返回的 assistant 消息（含 tool_calls）追加到对话
        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        })

        # 依次执行 tool_calls，把结果追加为 role=tool 消息
        for call in tool_calls:
            tool_name = call.get("function", {}).get("name", "")
            tool_args_raw = call.get("function", {}).get("arguments") or "{}"
            try:
                tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
            except json.JSONDecodeError:
                tool_args = {}

            handler = TOOL_HANDLERS.get(tool_name)
            if not handler:
                tool_result = f"未知工具：{tool_name}"
            else:
                try:
                    tool_result = await handler(**tool_args)
                except TypeError:
                    # 容错：参数对不上时不带参再试
                    tool_result = await handler()
                except Exception as exc:
                    logger.exception("tool %s execution failed", tool_name)
                    tool_result = f"工具 {tool_name} 执行出错：{exc}"

            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": tool_result,
            })
            logger.info("[wecom-llm] tool=%s args=%s len=%d", tool_name, tool_args, len(tool_result))

    return "❌ 工具调用循环超过上限，未能给出结论。"


async def _call_deepseek(messages: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "model": settings.deepseek_model or "deepseek-v4-flash",
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            settings.deepseek_api_url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
