"""数据库种子数据 — 插入示范商品分类、商品、规格、FAQ、配送说明.

使用方法:
    在服务器上运行:
    docker compose exec bot python -m bot.seeds
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from bot.models import async_session
from bot.models.faq import FaqItem, FaqType
from bot.models.product import Category, Product, ProductVariant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_data() -> None:
    """插入种子数据."""
    async with async_session() as session:
        # 检查是否已有数据
        result = await session.execute(text("SELECT COUNT(*) FROM categories"))
        count = result.scalar()
        if count and count > 0:
            logger.info("数据已存在，跳过种子插入 (categories=%d)", count)
            return

        logger.info("开始插入种子数据...")

        # ── 分类 ──────────────────────────────────────
        cat_electronics = Category(
            name_zh="📱 电子产品", name_en="📱 Electronics", name_ru="📱 Электроника",
            sort_order=1,
        )
        cat_accessories = Category(
            name_zh="🎧 配件周边", name_en="🎧 Accessories", name_ru="🎧 Аксессуары",
            sort_order=2,
        )
        cat_home = Category(
            name_zh="🏠 家居用品", name_en="🏠 Home & Living", name_ru="🏠 Домашний",
            sort_order=3,
        )
        session.add_all([cat_electronics, cat_accessories, cat_home])
        await session.flush()

        # ── 子分类 ────────────────────────────────────
        sub_phone = Category(
            parent_id=cat_electronics.id,
            name_zh="📲 手机", name_en="📲 Phones", name_ru="📲 Телефоны",
            sort_order=1,
        )
        sub_tablet = Category(
            parent_id=cat_electronics.id,
            name_zh="💻 平板", name_en="💻 Tablets", name_ru="💻 Планшеты",
            sort_order=2,
        )
        sub_earphone = Category(
            parent_id=cat_accessories.id,
            name_zh="🎧 耳机", name_en="🎧 Headphones", name_ru="🎧 Наушники",
            sort_order=1,
        )
        sub_case = Category(
            parent_id=cat_accessories.id,
            name_zh="📱 手机壳", name_en="📱 Phone Cases", name_ru="📱 Чехлы",
            sort_order=2,
        )
        session.add_all([sub_phone, sub_tablet, sub_earphone, sub_case])
        await session.flush()

        # ── 商品 ──────────────────────────────────────
        prod1 = Product(
            category_id=sub_phone.id,
            name_zh="华为 Mate 70 Pro", name_en="Huawei Mate 70 Pro", name_ru="Huawei Mate 70 Pro",
            description_zh="顶级旗舰手机，搭载麒麟芯片",
            description_en="Flagship smartphone with Kirin chipset",
            description_ru="Флагманский смартфон с чипом Kirin",
            sort_order=1,
        )
        prod2 = Product(
            category_id=sub_phone.id,
            name_zh="小米 15 Ultra", name_en="Xiaomi 15 Ultra", name_ru="Xiaomi 15 Ultra",
            description_zh="徕卡影像旗舰，性价比之王",
            description_en="Leica imaging flagship, best value",
            description_ru="Флагман с камерой Leica, лучшая цена",
            sort_order=2,
        )
        prod3 = Product(
            category_id=sub_tablet.id,
            name_zh="iPad Pro M4", name_en="iPad Pro M4", name_ru="iPad Pro M4",
            description_zh="专业级平板，超强性能",
            description_en="Professional tablet with extreme performance",
            description_ru="Профессиональный планшет с мощным процессором",
            sort_order=1,
        )
        prod4 = Product(
            category_id=sub_earphone.id,
            name_zh="AirPods Pro 3", name_en="AirPods Pro 3", name_ru="AirPods Pro 3",
            description_zh="主动降噪，空间音频",
            description_en="Active Noise Cancellation, Spatial Audio",
            description_ru="Активное шумоподавление, пространственный звук",
            sort_order=1,
        )
        session.add_all([prod1, prod2, prod3, prod4])
        await session.flush()

        # ── 规格与自动回复 ────────────────────────────
        variants = [
            ProductVariant(
                product_id=prod1.id, variant_key="256gb",
                name_zh="256GB 雅黑", name_en="256GB Black", name_ru="256GB Чёрный",
                auto_reply_zh="💰 批发价: ¥5,200 / $720\n📦 MOQ: 10台\n🚚 深圳发货 3-5天到莫斯科",
                auto_reply_en="💰 Wholesale: $720\n📦 MOQ: 10 units\n🚚 Shenzhen → Moscow 3-5 days",
                auto_reply_ru="💰 Оптовая цена: $720\n📦 MOQ: 10 шт.\n🚚 Шэньчжэнь → Москва 3-5 дней",
                sort_order=1,
            ),
            ProductVariant(
                product_id=prod1.id, variant_key="512gb",
                name_zh="512GB 雅金", name_en="512GB Gold", name_ru="512GB Золотой",
                auto_reply_zh="💰 批发价: ¥6,500 / $900\n📦 MOQ: 10台\n🚚 深圳发货 3-5天到莫斯科",
                auto_reply_en="💰 Wholesale: $900\n📦 MOQ: 10 units\n🚚 Shenzhen → Moscow 3-5 days",
                auto_reply_ru="💰 Оптовая цена: $900\n📦 MOQ: 10 шт.\n🚚 Шэньчжэнь → Москва 3-5 дней",
                sort_order=2,
            ),
            ProductVariant(
                product_id=prod2.id, variant_key="256gb",
                name_zh="256GB 黑色", name_en="256GB Black", name_ru="256GB Чёрный",
                auto_reply_zh="💰 批发价: ¥4,800 / $665\n📦 MOQ: 10台\n🚚 深圳发货 3-5天到莫斯科",
                auto_reply_en="💰 Wholesale: $665\n📦 MOQ: 10 units\n🚚 Shenzhen → Moscow 3-5 days",
                auto_reply_ru="💰 Оптовая цена: $665\n📦 MOQ: 10 шт.\n🚚 Шэньчжэнь → Москва 3-5 дней",
                sort_order=1,
            ),
            ProductVariant(
                product_id=prod3.id, variant_key="wifi_256",
                name_zh="WiFi 256GB", name_en="WiFi 256GB", name_ru="WiFi 256GB",
                auto_reply_zh="💰 批发价: ¥8,200 / $1,130\n📦 MOQ: 5台\n🚚 深圳发货 3-5天到莫斯科",
                auto_reply_en="💰 Wholesale: $1,130\n📦 MOQ: 5 units\n🚚 Shenzhen → Moscow 3-5 days",
                auto_reply_ru="💰 Оптовая цена: $1,130\n📦 MOQ: 5 шт.\n🚚 Шэньчжэнь → Москва 3-5 дней",
                sort_order=1,
            ),
            ProductVariant(
                product_id=prod4.id, variant_key="standard",
                name_zh="标准版", name_en="Standard", name_ru="Стандарт",
                auto_reply_zh="💰 批发价: ¥1,600 / $220\n📦 MOQ: 20个\n🚚 深圳发货 3-5天到莫斯科",
                auto_reply_en="💰 Wholesale: $220\n📦 MOQ: 20 units\n🚚 Shenzhen → Moscow 3-5 days",
                auto_reply_ru="💰 Оптовая цена: $220\n📦 MOQ: 20 шт.\n🚚 Шэньчжэнь → Москва 3-5 дней",
                sort_order=1,
            ),
        ]
        session.add_all(variants)

        # ── FAQ ───────────────────────────────────────
        faqs = [
            FaqItem(
                type=FaqType.FAQ,
                question_zh="你们支持哪些付款方式？",
                question_en="What payment methods do you accept?",
                question_ru="Какие способы оплаты вы принимаете?",
                answer_zh="我们支持以下付款方式：\n• 银行转账 (T/T)\n• 微信/支付宝\n• USDT\n• 西联汇款",
                answer_en="We accept:\n• Bank Transfer (T/T)\n• WeChat/Alipay\n• USDT\n• Western Union",
                answer_ru="Мы принимаем:\n• Банковский перевод (T/T)\n• WeChat/Alipay\n• USDT\n• Western Union",
                sort_order=1,
            ),
            FaqItem(
                type=FaqType.FAQ,
                question_zh="最低起订量是多少？",
                question_en="What is the minimum order quantity (MOQ)?",
                question_ru="Какой минимальный объём заказа (MOQ)?",
                answer_zh="不同产品 MOQ 不同，一般手机类 10 台起批，配件类 20 个起批。详情请查看具体产品页面或联系客服。",
                answer_en="MOQ varies: phones from 10 units, accessories from 20 units. Check product details or contact us.",
                answer_ru="MOQ зависит от товара: телефоны от 10 шт., аксессуары от 20 шт. Смотрите карточку товара или свяжитесь с нами.",
                sort_order=2,
            ),
            FaqItem(
                type=FaqType.FAQ,
                question_zh="你们提供售后保修吗？",
                question_en="Do you offer warranty?",
                question_ru="Вы предоставляете гарантию?",
                answer_zh="是的，所有产品享受 6 个月质保。如有质量问题可联系售后，我们将安排换货或退款。",
                answer_en="Yes, all products come with 6-month warranty. Contact after-sale support for replacements or refunds.",
                answer_ru="Да, на все товары гарантия 6 месяцев. Свяжитесь с поддержкой для замены или возврата.",
                sort_order=3,
            ),
        ]
        session.add_all(faqs)

        # ── 配送说明 ──────────────────────────────────
        deliveries = [
            FaqItem(
                type=FaqType.DELIVERY,
                question_zh="中国 → 莫斯科 空运",
                question_en="China → Moscow by Air",
                question_ru="Китай → Москва Авиа",
                answer_zh="🛫 空运专线\n• 时效: 3-5 个工作日\n• 费用: 按重量计算，约 $8-12/kg\n• 追踪: 支持全程追踪\n• 适合: 高价值、小体积商品",
                answer_en="🛫 Air Freight\n• Transit: 3-5 business days\n• Cost: ~$8-12/kg\n• Tracking: Full tracking\n• Suitable: High value, small items",
                answer_ru="🛫 Авиафрахт\n• Срок: 3-5 рабочих дней\n• Стоимость: ~$8-12/кг\n• Отслеживание: полное\n• Для: дорогих, компактных товаров",
                sort_order=1,
            ),
            FaqItem(
                type=FaqType.DELIVERY,
                question_zh="莫斯科本地仓发货 (CDEK / 俄邮)",
                question_en="Moscow Warehouse (CDEK / RU Post)",
                question_ru="Склад в Москве (СДЭК / Почта России)",
                answer_zh="📦 莫斯科仓发货\n• CDEK: 1-3 天到达俄罗斯大部分城市\n• 俄邮: 3-7 天，覆盖偏远地区\n• 费用: 根据重量和目的地计算",
                answer_en="📦 Moscow Warehouse\n• CDEK: 1-3 days to most Russian cities\n• RU Post: 3-7 days, remote areas\n• Cost: Based on weight & destination",
                answer_ru="📦 Склад Москва\n• СДЭК: 1-3 дня по России\n• Почта России: 3-7 дней, отдалённые районы\n• Стоимость: по весу и направлению",
                sort_order=2,
            ),
        ]
        session.add_all(deliveries)

        await session.commit()
        logger.info("✅ 种子数据插入完成!")


def main() -> None:
    """入口."""
    asyncio.run(seed_data())


if __name__ == "__main__":
    main()
