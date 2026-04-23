"""服务中心检修状态监听脚本.

每 5 分钟（由 docker-compose 的 sleep 控制）：
1. 读取服务中心 Google Sheet 全部检修记录
2. 对比 Redis 中存储的上次已知状态
3. 状态有变更 → 通过 Bot API 推送通知给已注册监听的用户

使用: python -m bot.repair_monitor
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.logging_config import setup_logging
from bot.services.service_center_sheet import (
    get_all_records,
    get_known_status,
    get_watcher_lang,
    get_watchers,
    set_known_status,
)

logger = logging.getLogger(__name__)

NOTIFY_TEXTS = {
    "zh": (
        "🔔 <b>检修状态更新</b>\n\n"
        "您的设备（CDEK: <code>{cdek_in}</code>）状态已更新：\n"
        "{emoji} {status}\n"
        "{cdek_out_line}"
    ),
    "en": (
        "🔔 <b>Repair Status Update</b>\n\n"
        "Your device (CDEK: <code>{cdek_in}</code>) status updated:\n"
        "{emoji} {status}\n"
        "{cdek_out_line}"
    ),
    "ru": (
        "🔔 <b>Обновление статуса ремонта</b>\n\n"
        "Статус вашего устройства (CDEK: <code>{cdek_in}</code>) изменён:\n"
        "{emoji} {status}\n"
        "{cdek_out_line}"
    ),
}

CDEK_OUT_LINE = {
    "zh": "📦 回寄单号：<code>{cdek_out}</code>\n",
    "en": "📦 Return CDEK: <code>{cdek_out}</code>\n",
    "ru": "📦 Номер CDEK возврата: <code>{cdek_out}</code>\n",
}


async def run_monitor() -> None:
    if not settings.service_center_sheet_id:
        logger.info("service_center_sheet_id not configured, skipping monitor run.")
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        records = await get_all_records()
    except Exception as e:
        logger.error("Failed to fetch repair records: %s", e)
        await bot.session.close()
        return

    notified = 0
    for record in records:
        cdek_no = record.cdek_in
        current_status = record.status or ""
        known_status = await get_known_status(cdek_no)

        if current_status == known_status:
            continue

        # 状态变更，更新 Redis 并通知监听用户
        await set_known_status(cdek_no, current_status)
        watchers = await get_watchers(cdek_no)
        if not watchers:
            continue

        for user_id in watchers:
            lang = await get_watcher_lang(cdek_no, user_id)
            cdek_out_part = ""
            if record.cdek_out:
                cdek_out_part = CDEK_OUT_LINE.get(lang, CDEK_OUT_LINE["zh"]).format(cdek_out=record.cdek_out)
            text = NOTIFY_TEXTS.get(lang, NOTIFY_TEXTS["zh"]).format(
                cdek_in=cdek_no,
                emoji=record.status_emoji(),
                status=current_status or "-",
                cdek_out_line=cdek_out_part,
            )
            try:
                await bot.send_message(user_id, text)
                notified += 1
            except Exception as e:
                logger.warning("Failed to notify user %d: %s", user_id, e)

    logger.info("Monitor run complete. Records: %d, Notified: %d", len(records), notified)
    await bot.session.close()


def main() -> None:
    setup_logging()
    asyncio.run(run_monitor())


if __name__ == "__main__":
    main()
