"""企业微信智能机器人 WebSocket 长连接客户端。

协议参考：https://developer.work.weixin.qq.com/document/path/101463

帧格式：
    {
      "cmd": "<命令名>",
      "headers": {"req_id": "..."},
      "body": {...}
    }

关键命令：
    aibot_subscribe                — 客户端 → 服务端，带 bot_id+secret 鉴权
    aibot_msg_callback             — 服务端 → 客户端，用户发来消息
    aibot_event_callback           — 服务端 → 客户端，事件（首次进入会话等）
    aibot_respond_msg              — 客户端 → 服务端，回复消息
    aibot_respond_welcome_msg      — 客户端 → 服务端，回复欢迎语
    aibot_respond_stream_msg       — 客户端 → 服务端，流式回复增量

具体帧名以服务端实际接受为准，遇到错误日志时可调整。
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import string
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from bot.config import settings

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # 秒，文档建议
RECONNECT_BASE_DELAY = 3
RECONNECT_MAX_DELAY = 60


def _gen_req_id(prefix: str = "req") -> str:
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    return f"{prefix}_{rand}"


class WecomBotClient:
    """长连接客户端：连接 → 订阅 → 心跳 → 收消息 → 调度回调 → 自动重连."""

    def __init__(
        self,
        bot_id: str,
        secret: str,
        ws_url: str,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.secret = secret
        self.ws_url = ws_url
        self.on_message = on_message
        self.on_event = on_event
        self.ws: Any = None
        self._closing = False

    async def run_forever(self) -> None:
        delay = RECONNECT_BASE_DELAY
        while not self._closing:
            try:
                await self._run_once()
                delay = RECONNECT_BASE_DELAY  # 成功一次重置退避
            except (ConnectionClosed, WebSocketException, asyncio.TimeoutError) as exc:
                logger.warning("[wecom-ws] 连接断开: %s", exc)
            except Exception:
                logger.exception("[wecom-ws] run_once 异常")
            if self._closing:
                break
            logger.info("[wecom-ws] %ds 后重连…", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _run_once(self) -> None:
        logger.info("[wecom-ws] 连接 %s", self.ws_url)
        async with websockets.connect(self.ws_url, ping_interval=None) as ws:
            self.ws = ws
            await self._subscribe()
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            try:
                async for raw in ws:
                    await self._handle_raw(raw)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                self.ws = None

    async def _subscribe(self) -> None:
        frame = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": _gen_req_id("sub")},
            "body": {"bot_id": self.bot_id, "secret": self.secret},
        }
        await self._send(frame)
        logger.info("[wecom-ws] 已发送订阅帧 bot_id=%s", self.bot_id[:6] + "…")

    async def _heartbeat_loop(self) -> None:
        """业务层心跳：发 cmd=aibot_ping 的 JSON 帧。

        企业微信不接受 WebSocket 协议层 ping（会触发 1002 protocol error）。
        """
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self.ws is None:
                    return
                try:
                    await self._send({
                        "cmd": "aibot_ping",
                        "headers": {"req_id": _gen_req_id("hb")},
                        "body": {},
                    })
                except Exception as e:
                    logger.warning("[wecom-ws] 心跳发送失败: %s", e)
                    return
        except asyncio.CancelledError:
            return

    async def _handle_raw(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[wecom-ws] 收到非 JSON 帧: %r", raw[:120])
            return

        cmd = frame.get("cmd", "")
        body = frame.get("body") or {}
        logger.info(
            "[wecom-ws] 收到 cmd=%s req_id=%s body_keys=%s",
            cmd,
            frame.get("headers", {}).get("req_id", ""),
            list(body.keys()),
        )

        if cmd == "aibot_msg_callback":
            try:
                await self.on_message(frame)
            except Exception:
                logger.exception("on_message 处理失败")
        elif cmd == "aibot_event_callback":
            if self.on_event:
                try:
                    await self.on_event(frame)
                except Exception:
                    logger.exception("on_event 处理失败")
        elif cmd.endswith("_resp") or cmd.endswith("_ack") or "pong" in cmd or "ping" in cmd:
            # 服务端的响应/心跳确认，打印简略信息
            err_code = body.get("errcode") if isinstance(body, dict) else None
            err_msg = body.get("errmsg") if isinstance(body, dict) else None
            if err_code:
                logger.warning("[wecom-ws] %s 错误 code=%s msg=%s", cmd, err_code, err_msg)
            else:
                logger.info("[wecom-ws] %s body=%s", cmd, body)
        else:
            logger.info("[wecom-ws] 未知 cmd=%s body=%s", cmd, body)

    async def _send(self, frame: dict[str, Any]) -> None:
        if self.ws is None:
            raise RuntimeError("WebSocket 未连接")
        await self.ws.send(json.dumps(frame, ensure_ascii=False))

    @staticmethod
    def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if v is not None}

    async def reply_text(self, original_frame: dict[str, Any], text: str) -> None:
        """对一条 aibot_msg_callback 用流式帧一次性发完整文本。

        长连接模式回复必须用 msgtype=stream + stream.{id, finish, content} 嵌套结构，
        不能用平铺字段。
        """
        body_in = original_frame.get("body") or {}
        stream_id = _gen_req_id("stream")
        base_body = self._strip_none({
            "msgid": body_in.get("msgid"),
            "aibotid": body_in.get("aibotid"),
            "chatid": body_in.get("chatid"),
            "msgtype": "stream",
        })
        # 第一帧：发内容，finish=false
        await self._send({
            "cmd": "aibot_respond_stream_msg",
            "headers": {"req_id": _gen_req_id("rsp")},
            "body": {
                **base_body,
                "stream": {"id": stream_id, "content": text, "finish": False},
            },
        })
        # 第二帧：空内容 + finish=true 收尾
        await self._send({
            "cmd": "aibot_respond_stream_msg",
            "headers": {"req_id": _gen_req_id("rsp")},
            "body": {
                **base_body,
                "stream": {"id": stream_id, "content": "", "finish": True},
            },
        })
        logger.info("[wecom-ws] 已回复消息 stream_id=%s len=%d", stream_id, len(text))

    async def reply_welcome(self, original_frame: dict[str, Any], text: str) -> None:
        body_in = original_frame.get("body") or {}
        body = self._strip_none({
            "aibotid": body_in.get("aibotid"),
            "chatid": body_in.get("chatid"),
            "msgtype": "text",
            "text": {"content": text},
        })
        await self._send({
            "cmd": "aibot_respond_welcome_msg",
            "headers": {"req_id": _gen_req_id("welcome")},
            "body": body,
        })

    async def close(self) -> None:
        self._closing = True
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
