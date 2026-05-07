import hashlib
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import select

from bot.models import async_session
from bot.models.ae_store_cookie import AEStoreCookie

logger = logging.getLogger(__name__)


DEFAULT_CHANNEL_ID = "238299"


async def load_store(store_name: str) -> tuple[str, str]:
    """从数据库读取店铺的 (cookie, channel_id)。"""
    async with async_session() as session:
        row = await session.scalar(
            select(AEStoreCookie).where(AEStoreCookie.store_name == store_name)
        )
        if row:
            return row.cookie, (row.channel_id or DEFAULT_CHANNEL_ID)
        return "", DEFAULT_CHANNEL_ID


async def load_cookie(store_name: str) -> str:
    cookie, _ = await load_store(store_name)
    return cookie


async def save_cookie(store_name: str, cookie_str: str) -> None:
    """将 Cookie 写入数据库（不存在则新建，存在则更新）。"""
    async with async_session() as session:
        row = await session.scalar(
            select(AEStoreCookie).where(AEStoreCookie.store_name == store_name)
        )
        if row:
            row.cookie = cookie_str
        else:
            session.add(AEStoreCookie(store_name=store_name, cookie=cookie_str))
        await session.commit()
    logger.info("[ae-mtop] Cookie 已保存到数据库 store=%s", store_name)


async def save_channel_id(store_name: str, channel_id: str) -> None:
    """更新店铺的 channel_id。"""
    async with async_session() as session:
        row = await session.scalar(
            select(AEStoreCookie).where(AEStoreCookie.store_name == store_name)
        )
        if row:
            row.channel_id = channel_id
            await session.commit()
            logger.info("[ae-mtop] channel_id 已更新 store=%s channel_id=%s", store_name, channel_id)


class MTOPClient:
    """速卖通网页端 MTOP / H5API 客户端，多店铺版本。"""

    def __init__(self, store_name: str, cookie_str: str, channel_id: str = DEFAULT_CHANNEL_ID) -> None:
        self.store_name = store_name
        self.cookie_str = cookie_str
        self.channel_id = channel_id
        self.app_key = "30267743"
        self.gateway = "https://seller-acs.aliexpress.com/h5/{api}/1.0/"

    @classmethod
    async def create(cls, store_name: str) -> "MTOPClient":
        """异步工厂方法：从数据库加载 Cookie + channel_id 后创建实例。"""
        cookie_str, channel_id = await load_store(store_name)
        return cls(store_name, cookie_str, channel_id)

    def _get_tk(self) -> str:
        for item in self.cookie_str.split(";"):
            item = item.strip()
            if item.startswith("_m_h5_tk="):
                full_tk = item.split("=", 1)[1]
                return full_tk.split("_")[0]
        return ""

    def _sign(self, token: str, t: str, data: str) -> str:
        sign_str = f"{token}&{t}&{self.app_key}&{data}"
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    async def _update_cookie_str(self, new_cookies: httpx.Cookies) -> bool:
        """解析响应 Cookie，回写 _m_h5_tk 并持久化到数据库。"""
        cookie_dict: dict[str, str] = {}
        for item in self.cookie_str.split(";"):
            item = item.strip()
            if not item:
                continue
            parts = item.split("=", 1)
            if len(parts) == 2:
                cookie_dict[parts[0]] = parts[1]

        changed = False
        if "_m_h5_tk" in new_cookies:
            cookie_dict["_m_h5_tk"] = new_cookies["_m_h5_tk"]
            changed = True
        if "_m_h5_tk_enc" in new_cookies:
            cookie_dict["_m_h5_tk_enc"] = new_cookies["_m_h5_tk_enc"]
            changed = True

        if changed:
            self.cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
            await save_cookie(self.store_name, self.cookie_str)
            logger.info("[ae-mtop] 自动续命：_m_h5_tk 已更新 store=%s", self.store_name)
        return changed

    async def request(self, api: str, data_dict: dict[str, Any]) -> dict:
        if not self.cookie_str:
            raise ValueError("SESSION_EXPIRED")

        t = str(int(time.time() * 1000))
        data_str = json.dumps(data_dict, separators=(",", ":"))
        token = self._get_tk()
        sign = self._sign(token, t, data_str)
        url = self.gateway.format(api=api)

        params = {
            "jsv": "2.7.5", "appKey": self.app_key, "t": t, "sign": sign,
            "type": "originaljson", "api": api, "v": "1.0", "dataType": "json",
            "__channel-id__": self.channel_id,
        }
        payload = {"data": data_str}
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": self.cookie_str,
            "origin": "https://csp.aliexpress.com",
            "referer": "https://csp.aliexpress.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/147.0.0.0"
            ),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, data=payload, headers=headers)

            if response.cookies:
                refreshed = await self._update_cookie_str(response.cookies)
                if refreshed:
                    token = self._get_tk()
                    t = str(int(time.time() * 1000))
                    sign = self._sign(token, t, data_str)
                    params.update({"t": t, "sign": sign})
                    headers["cookie"] = self.cookie_str
                    response = await client.post(url, params=params, data=payload, headers=headers)
                    if response.cookies:
                        await self._update_cookie_str(response.cookies)

            response.raise_for_status()
            res_json = response.json()

            ret_msg = str(res_json.get("ret", []))
            if any(k in ret_msg for k in [
                "FAIL_SYS_SESSION_EXPIRED", "FAIL_SYS_TOKEN_EMPTY",
                "未登录", "EXOIRED", "EXPIRED",
            ]):
                raise ValueError("SESSION_EXPIRED")

            return res_json
