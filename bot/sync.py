"""库存同步脚本 — 独立运行入口.

用法：
    python -m bot.sync                # 默认仅同步 Outdoor gid=0 库存表
    python -m bot.sync outdoor_vip    # 仅同步 gid=0 库存表
    python -m bot.sync outdoor_public # 仅同步公开表

cron 示例（每小时执行）：
    0 * * * * cd /app && python -m bot.sync >> /var/log/inventory_sync.log 2>&1
"""

from __future__ import annotations

import asyncio
import sys
import time


async def _run(sheet_keys: list[str] | None = None) -> int:
    """执行同步，返回退出码（0=成功，1=有失败）."""
    from bot.services.inventory_sync import sync_all_sheets, sync_sheet

    start = time.monotonic()

    if sheet_keys:
        results = [await sync_sheet(k) for k in sheet_keys]
    else:
        results = await sync_all_sheets()

    elapsed = time.monotonic() - start
    has_error = False

    for r in results:
        if r.error:
            print(f"[FAIL] {r.sheet_key}: {r.error}")
            has_error = True
        else:
            print(
                f"[OK]   {r.sheet_key}: "
                f"{r.updated_rows}/{r.total_skus} 行更新  "
                f"(聚水潭 {r.jst_found} 条 / 跨运宝 {r.kyb_found} 条)"
            )

    print(f"\n耗时 {elapsed:.1f}s  |  {'失败' if has_error else '全部成功'}")
    return 1 if has_error else 0


def main() -> None:
    sheet_keys = sys.argv[1:] or None
    exit_code = asyncio.run(_run(sheet_keys))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
