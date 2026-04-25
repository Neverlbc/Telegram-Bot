#!/bin/bash
set -e

echo "Ensuring database tables exist..."
python -c "
import asyncio
from bot.models import Base
from bot.models.user import User
from bot.models.product import Category, Product, ProductVariant
from bot.models.faq import FaqItem
from bot.models.order import WholesaleOrder, AftersaleQuery, LogisticsQuery
from bot.models.device import DeviceSerialQuery, DeviceTicket
from bot.models.ticket import SupportTicket, SupportMessage
from sqlalchemy.ext.asyncio import create_async_engine
from bot.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(main())
" && echo "Database ready." || echo "WARNING: Database setup failed (may need manual intervention)"

if [ "$#" -gt 0 ]; then
    echo "Starting custom command: $*"
    exec "$@"
fi

echo "Starting bot..."
exec python -m bot
