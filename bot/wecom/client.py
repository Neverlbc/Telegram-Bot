"""企业微信智能机器人 WebSocket 长连接客户端。

协议参考：https://developer.work.weixin.qq.com/document/path/101463

帧格式：
    {
      "cmd": "<命令名>",
      "headers": {"req_id": "..."},
      "body": {...}
    }

关键命令：
    aibot_subscribe            — 客户端 → 服务端，带 bot_id+secret 鉴权
    aibot_msg_callback         — 服务端 → 客户端，用户发来消息
    aibot_event_callback       — 服务端 → 客户端，事件（首次进入会话等）
    aibot_respond_msg          — 客户端 → 服务端，回复消息（含流式）
    aibot_respond_welcome_msg  — 客户端 → 服务端，回复欢迎语

回复规则（长连接模式）：
    - headers.req_id 必须与原始消息相同，企业微信用它关联响应
    - body 只需 {msgtype: "stream", stream: {id, content, finish}}
    - stream.id 相同的帧构成一条流式消息；finish=true 结束并锁定内容
    - response_url 仅供 HTTP 回调模式使用，长连接模式勿用
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
                delay = RECONNECT_BASE_DELAY
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

    def new_stream_id(self) -> str:
        return _gen_req_id("stream")

    async def reply_stream(
        self,
        original_frame: dict[str, Any],
        stream_id: str,
        content: str,
        finish: bool,
    ) -> None:
        """发送一帧流式回复。

        req_id 必须与原始消息一致；stream_id 相同的帧构成一条流式消息。
        finish=False 创建/更新占位内容；finish=True 最终锁定。
        """
        req_id = original_frame.get("headers", {}).get("req_id") or _gen_req_id("rsp")
        await self._send({
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": req_id},
            "body": {
                "msgtype": "stream",
                "stream": {"id": stream_id, "content": content, "finish": finish},
            },
        })

    async def reply_text(
        self,
        original_frame: dict[str, Any],
        text: str,
        stream_id: str | None = None,
    ) -> None:
        """用 stream_id 回复完整文本（finish=True 一帧结束）。

        若已提前发过 finish=False 占位帧，传入相同 stream_id 可让企业微信
        客户端用最终内容替换占位文字。
        """
        sid = stream_id or _gen_req_id("stream")
        await self.reply_stream(original_frame, sid, text, True)
        logger.info("[wecom-ws] 已回复 stream_id=%s len=%d", sid, len(text))

    async def reply_welcome(self, original_frame: dict[str, Any], text: str) -> None:
        body_in = original_frame.get("body") or {}
        body: dict[str, Any] = {"msgtype": "text", "text": {"content": text}}
        aibotid = body_in.get("aibotid")
        chatid = body_in.get("chatid")
        if aibotid:
            body["aibotid"] = aibotid
        if chatid:
            body["chatid"] = chatid
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
