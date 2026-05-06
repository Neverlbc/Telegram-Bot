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

        # 把 LLM 返回的整条 assistant 消息追加回去（保留 reasoning_content / tool_calls /
        # content 等所有字段）。DeepSeek V4 思考模式下，tool-call 轮次的 reasoning_content
        # 必须原样回传，否则 400：`The reasoning_content in the thinking mode must be
        # passed back to the API.`
        assistant_msg = dict(message)  # 浅拷贝，避免被后续修改
        assistant_msg.setdefault("role", "assistant")
        if assistant_msg.get("content") in (None, ""):
            # OpenAI 规范：有 tool_calls 时 content 可为 null
            assistant_msg["content"] = None
        messages.append(assistant_msg)

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
                    tool_result = await handler()
                except Exception as exc:
                    logger.exception("tool %s execution failed", tool_name)
                    tool_result = f"工具 {tool_name} 执行出错：{exc}"

            tool_call_id = call.get("id") or call.get("tool_call_id") or ""
            if not tool_call_id:
                # DeepSeek 必须有 tool_call_id 配对，否则 400
                logger.warning("[wecom-llm] tool_call 缺 id，强行生成占位值")
                tool_call_id = f"call_{tool_name}"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": str(tool_result) if tool_result else "(空)",
            })
            logger.info("[wecom-llm] tool=%s id=%s args=%s len=%d",
                        tool_name, tool_call_id, tool_args, len(tool_result))

    return "❌ 工具调用循环超过上限，未能给出结论。"


async def _call_deepseek(messages: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "model": settings.deepseek_model or "deepseek-chat",
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
            text = await resp.text()
            if resp.status >= 400:
                logger.error(
                    "DeepSeek HTTP %s body=%s payload_messages=%s",
                    resp.status, text[:1000],
                    [{"role": m.get("role"), "has_content": bool(m.get("content")),
                      "has_tool_calls": bool(m.get("tool_calls")),
                      "tool_call_id": m.get("tool_call_id", "")} for m in messages],
                )
                raise RuntimeError(f"DeepSeek {resp.status}: {text[:300]}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                raise RuntimeError(f"DeepSeek 返回非 JSON: {text[:300]}")
