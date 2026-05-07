import time
import json
import hashlib
import httpx
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cookie 的持久化存储文件位置
COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'ae_cookies.json')

def load_cookie(store_name: str) -> str:
    """加载指定店铺的 Cookie"""
    if not os.path.exists(COOKIE_FILE):
        return ""
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get(store_name, "")
    except Exception as e:
        logger.error(f"读取 Cookie 文件失败: {e}")
        return ""

def save_cookie(store_name: str, cookie_str: str):
    """保存指定店铺的 Cookie"""
    data = {}
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass
    data[store_name] = cookie_str
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class MTOPClient:
    """
    专门用于对接速卖通网页端 Mtop / H5API，集成了自动提取与保存 _m_h5_tk 的功能。
    多店铺版本。
    """
    def __init__(self, store_name: str):
        self.store_name = store_name
        self.cookie_str = load_cookie(store_name)
        self.app_key = "30267743" 
        self.gateway = "https://seller-acs.aliexpress.com/h5/{api}/1.0/"

    def _get_tk(self) -> str:
        """从 cookie 中提取 _m_h5_tk 的前半部分"""
        for item in self.cookie_str.split(";"):
            item = item.strip()
            if item.startswith("_m_h5_tk="):
                full_tk = item.split("=")[1]
                return full_tk.split("_")[0]
        return ""

    def _sign(self, token: str, t: str, data: str) -> str:
        """MD5(token&t&appKey&data)"""
        sign_str = f"{token}&{t}&{self.app_key}&{data}"
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

    def update_cookie_str(self, new_cookies: httpx.Cookies) -> bool:
        """解析 Response 中的新 Cookie 回写，防线一：自动续命"""
        changed = False
        cookie_dict = {}
        for item in self.cookie_str.split(";"):
            item = item.strip()
            if not item: continue
            parts = item.split("=", 1)
            if len(parts) == 2:
                cookie_dict[parts[0]] = parts[1]

        if "_m_h5_tk" in new_cookies:
            cookie_dict["_m_h5_tk"] = new_cookies["_m_h5_tk"]
            changed = True
        if "_m_h5_tk_enc" in new_cookies:
            cookie_dict["_m_h5_tk_enc"] = new_cookies["_m_h5_tk_enc"]
            changed = True

        if changed:
            self.cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            save_cookie(self.store_name, self.cookie_str)
            logger.info(f"[{self.store_name}] 自动捕获并更新了 _m_h5_tk Cookie，续命成功！")
        return changed

    async def request(self, api: str, data_dict: dict[str, Any]) -> dict:
        """发起异步 MTOP 请求"""
        if not self.cookie_str:
            raise ValueError("SESSION_EXPIRED")

        t = str(int(time.time() * 1000))
        data_str = json.dumps(data_dict, separators=(',', ':'))
        token = self._get_tk()
        sign = self._sign(token, t, data_str)
        url = self.gateway.format(api=api)
        
        params = {
            "jsv": "2.7.5", "appKey": self.app_key, "t": t, "sign": sign,
            "type": "originaljson", "api": api, "v": "1.0", "dataType": "json",
            "__channel-id__": "238299"
        }
        payload = {"data": data_str}
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": self.cookie_str,
            "origin": "https://csp.aliexpress.com",
            "referer": "https://csp.aliexpress.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, data=payload, headers=headers)
            
            # 第一道防线：检测是否需要刷新 h5_token
            if response.cookies:
                token_refreshed = self.update_cookie_str(response.cookies)
                # 如果发现更新了 token，当前请求大概率是报 INVALID_SIGN 的，无缝重试一次！
                if token_refreshed:
                    token = self._get_tk()
                    t = str(int(time.time() * 1000))
                    sign = self._sign(token, t, data_str)
                    params.update({"t": t, "sign": sign})
                    headers["cookie"] = self.cookie_str # 更新头部
                    response = await client.post(url, params=params, data=payload, headers=headers)
                    if response.cookies:
                        self.update_cookie_str(response.cookies)
                        
            response.raise_for_status()
            res_json = response.json()
            
            ret_msg = str(res_json.get("ret", []))
            
            # 第二道防线：判断长期有效票据是否死亡
            if any(k in ret_msg for k in ["FAIL_SYS_SESSION_EXPIRED", "FAIL_SYS_TOKEN_EMPTY", "未登录", "EXOIRED", "EXPIRED"]):
                raise ValueError("SESSION_EXPIRED")
                
            return res_json
