"""OpenAI 驱动的描述翻译服务（带 Redis 长缓存）。

用于将 Google Sheet 里的俄语商品描述翻译成用户当前 UI 语言。
- 缓存键：desc_trans:<lang>:<md5(text)>，TTL=30 天
- 批量翻译：一次 API 调用处理多条描述（用 JSON 数组传输）
- 失败回退：API 异常时返回原文
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 天
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
LANG_NAMES = {
    "zh": "Chinese (Simplified)",
    "en": "English",
    "ru": "Russian",
}


def _cache_key(text: str, target_lang: str) -> str:
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"desc_trans:{target_lang}:{digest}"


async def _redis_client() -> Any | None:
    """获取共享 Redis 客户端（与 outdoor_sheets 同一个池）."""
    try:
        from bot.services.outdoor_sheets import _get_redis  # type: ignore
    except Exception:
        return None
    return _get_redis()


async def _load_cached(texts: list[str], target_lang: str) -> dict[str, str]:
    redis = await _redis_client()
    if redis is None:
        return {}
    result: dict[str, str] = {}
    keys = [_cache_key(t, target_lang) for t in texts]
    try:
        values = await redis.mget(*keys)
    except Exception as e:
        logger.warning("translation cache mget failed: %s", e)
        return {}
    for text, value in zip(texts, values):
        if value:
            result[text] = value
    return result


async def _save_cached(mapping: dict[str, str], target_lang: str) -> None:
    redis = await _redis_client()
    if redis is None:
        return
    try:
        pipe = redis.pipeline()
        for original, translated in mapping.items():
            if translated:
                pipe.set(_cache_key(original, target_lang), translated, ex=CACHE_TTL_SECONDS)
        await pipe.execute()
    except Exception as e:
        logger.warning("translation cache set failed: %s", e)


async def _call_openai(texts: list[str], target_lang: str) -> list[str]:
    """调用 OpenAI 批量翻译，返回与输入等长的翻译列表（失败返回空列表）."""
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY 未配置，跳过翻译")
        return []

    target_name = LANG_NAMES.get(target_lang, target_lang)
    prompt = (
        f"Translate the following product descriptions into {target_name}. "
        "These are short descriptions for outdoor / thermal-imaging gear. "
        "Keep it concise and natural. "
        "Return ONLY a JSON array of strings in the same order as input, no other text, no markdown.\n\n"
        f"INPUT: {json.dumps(texts, ensure_ascii=False)}"
    )

    payload = {
        "model": settings.openai_model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a precise product-catalog translator."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENAI_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception as e:
        logger.warning("OpenAI translation request failed: %s", e)
        return []

    try:
        content = data["choices"][0]["message"]["content"].strip()
        # 模型偶尔会包 markdown，剥掉
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()
        translations = json.loads(content)
        if not isinstance(translations, list) or len(translations) != len(texts):
            logger.warning("OpenAI returned %d items for %d inputs", len(translations), len(texts))
            return []
        return [str(t) for t in translations]
    except Exception as e:
        logger.warning("OpenAI translation parse failed: %s; raw=%r", e, data)
        return []


async def translate_batch(texts: list[str], target_lang: str) -> dict[str, str]:
    """将文本列表翻译成目标语言。返回 {原文: 译文}。

    - 目标语言为 ru 或文本为空时直接返回原文映射
    - 命中缓存的不调 API
    - API 失败时缺失项映射回原文
    """
    unique_texts = list({(t or "").strip() for t in texts if (t or "").strip()})
    result: dict[str, str] = {t: t for t in unique_texts}

    if target_lang == "ru" or not unique_texts:
        return result

    cached = await _load_cached(unique_texts, target_lang)
    result.update(cached)

    missing = [t for t in unique_texts if t not in cached]
    if not missing:
        return result

    translations = await _call_openai(missing, target_lang)
    if translations and len(translations) == len(missing):
        new_map = {original: translated for original, translated in zip(missing, translations) if translated}
        result.update(new_map)
        await _save_cached(new_map, target_lang)

    return result
