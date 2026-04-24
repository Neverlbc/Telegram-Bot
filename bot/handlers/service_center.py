"""A-BF 俄罗斯服务中心.

功能：
1. 服务中心说明（静态文本）
2. 服务中心 TG 入口链接
3. 设备检修查询（输入 CDEK 单号 → 查 Google 表 → 返回状态 + 订阅状态变更）
4. 管理员入口（密码 service2026adminXXA → 后台隐藏菜单）
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import ServiceCenterCallback
from bot.keyboards.inline import (
    nav_buttons,
    service_center_admin_keyboard,
    service_center_menu_keyboard,
)
from bot.services.service_center_sheet import (
    get_all_records,
    get_repair_status,
    register_watcher,
)
from bot.states.service_center import ServiceCenterStates

logger = logging.getLogger(__name__)
router = Router(name="service_center")

# ── 多语言文案 ──────────────────────────────────────────

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "menu_title": "🛠 <b>A-BF 俄罗斯服务中心</b>\n\n请选择服务：",
        "info_text": (
            "👋您好，这里是俄罗斯A-BF服务中心！\n\n"
            "我们接受从本公司购买的产品进行维修和检测。\n\n"
            "如需更多信息，请私信联系我们。\n\n"
            "🕒 服务时间：周一至周五，上午9:30至下午6:00（莫斯科时间）。\n\n"
            "❗️请注意：我们的服务中心仅提供技术支持和设备维修服务。我们不提供关于卖家查询、订单状态或发货信息的咨询。联系我们时，请勿提供卖家信息或订单号。\n\n"
            "📩 为确保快速解决问题，请提供以下信息：\n\n"
            "1. 设备型号\n"
            "2. 设备序列号 (S/N)\n"
            "3. 故障或问题的描述\n\n"
            "💬 由于服务中心工作量较大，回复可能会有所延迟。我们所有员工均为来自俄罗斯的俄语专家。我们会在工作时间内按先到先得的原则回复您。\n\n"
            "感谢您的理解和耐心！"
        ),
        "enter_cdek": "🔧 <b>设备检修查询</b>\n\n请输入您寄件的 CDEK 单号：",
        "cdek_not_found": "❓ 未找到单号 <code>{cdek_no}</code> 的记录。\n\n请确认单号是否正确，或联系客服：",
        "cdek_result": (
            "🔧 <b>检修状态查询结果</b>\n\n"
            "CDEK 单号：<code>{cdek_in}</code>\n"
            "设备型号：{model}\n"
            "序列号：{sn}\n"
            "检修状态：{emoji} {status}\n"
            "{cdek_out_line}"
            "\n✅ 已订阅状态更新，有变更时将自动通知您。"
        ),
        "cdek_out_line": "回寄单号：<code>{cdek_out}</code>\n",
        "enter_admin_pw": "🔐 请输入管理员密码：",
        "wrong_admin_pw": "❌ 密码错误。",
        "admin_title": "🔐 <b>服务中心管理后台</b>\n\n请选择操作：",
        "sn_list_title": "📋 <b>SN 表（全部检修记录）</b>\n\n",
        "sn_list_empty": "📭 暂无检修记录。",
        "not_configured": "⚠️ 服务中心 Google Sheet 未配置，请联系管理员。",
        "contact_cs": "💬 联系客服",
        "loading_err": "❌ 查询失败，请稍后重试。",
    },
    "en": {
        "menu_title": "🛠 <b>A-BF Russia Service Center</b>\n\nSelect a service:",
        "info_text": (
            "👋Hello, this is the Russian A-BF Service Center!\n\n"
            "We accept products purchased from our company for repair and inspection.\n\n"
            "For more information, please send a private message to the community.\n\n"
            "🕒 Hours: Mon–Fri, 9:30 AM to 6:00 PM (Moscow time).\n\n"
            "❗️ Please note: Our service center provides technical support and equipment repairs only. "
            "We do not provide advice on seller inquiries, order status, or delivery information. "
            "When contacting us, please do not provide seller information or the order number.\n\n"
            "📩 To ensure a prompt resolution, please provide the following:\n\n"
            "1. Equipment model\n"
            "2. Device serial number (S/N)\n"
            "3. Description of the malfunction or problem encountered\n\n"
            "💬 Due to the high workload of our service center, there may be a delay in response. "
            "All our employees are Russian-speaking specialists from Russia. "
            "We will respond to you during business hours on a first-come, first-served basis.\n\n"
            "Thank you for your understanding and patience!"
        ),
        "enter_cdek": "🔧 <b>Device Repair Query</b>\n\nPlease enter your outgoing CDEK tracking number:",
        "cdek_not_found": "❓ No record found for <code>{cdek_no}</code>.\n\nPlease verify the number or contact support:",
        "cdek_result": (
            "🔧 <b>Repair Status</b>\n\n"
            "CDEK No.: <code>{cdek_in}</code>\n"
            "Model: {model}\n"
            "SN: {sn}\n"
            "Status: {emoji} {status}\n"
            "{cdek_out_line}"
            "\n✅ Subscribed to updates — you'll be notified on any change."
        ),
        "cdek_out_line": "Return CDEK No.: <code>{cdek_out}</code>\n",
        "enter_admin_pw": "🔐 Enter admin password:",
        "wrong_admin_pw": "❌ Incorrect password.",
        "admin_title": "🔐 <b>Service Center Admin</b>\n\nSelect an action:",
        "sn_list_title": "📋 <b>SN List (all repair records)</b>\n\n",
        "sn_list_empty": "📭 No repair records found.",
        "not_configured": "⚠️ Service center sheet not configured. Contact admin.",
        "contact_cs": "💬 Contact Support",
        "loading_err": "❌ Query failed. Please try again later.",
    },
    "ru": {
        "menu_title": "🛠 <b>Сервисный центр A-BF</b>\n\nВыберите услугу:",
        "info_text": (
            "👋Здравствуйте, это Российский сервисный центр А-BF！\n\n"
            "Мы принимаем к ремонту и осмотру продукцию, приобретенную у нашей компании.\n\n"
            "Для уточнения вы можете написать в личные сообщения сообществу.\n\n"
            "🕒 Режим работы: Пн–Пт, с 09:30 до 18:00 (по московскому времени).\n\n"
            "❗️ Обратите внимание: наш сервисный центр занимается исключительно технической поддержкой и ремонтом оборудования. "
            "Мы не консультируем по вопросам продавца, статусу заказа или доставки. "
            "При обращении не нужно указывать данные продавца или номер заказа.\n\n"
            "📩 Для оперативного решения вопроса, пожалуйста, сразу укажите:\n\n"
            "1. Модель оборудования\n"
            "2. Серийный номер прибора (S/N)\n"
            "3. Описание неисправности или возникшей проблемы\n\n"
            "💬 В связи с высокой загрузкой сервисного центра возможны задержки в ответе. "
            "Все наши сотрудники — русскоязычные специалисты из России. "
            "Мы ответим вам в рабочее время в порядке очереди.\n\n"
            "Спасибо за понимание и терпение！"
        ),
        "enter_cdek": "🔧 <b>Запрос ремонта</b>\n\nВведите номер CDEK вашего отправления:",
        "cdek_not_found": "❓ Запись для <code>{cdek_no}</code> не найдена.\n\nПроверьте номер или обратитесь в поддержку:",
        "cdek_result": (
            "🔧 <b>Статус ремонта</b>\n\n"
            "Номер CDEK: <code>{cdek_in}</code>\n"
            "Модель: {model}\n"
            "Серийный номер: {sn}\n"
            "Статус: {emoji} {status}\n"
            "{cdek_out_line}"
            "\n✅ Вы подписаны на обновления — уведомим при изменении."
        ),
        "cdek_out_line": "Номер CDEK для возврата: <code>{cdek_out}</code>\n",
        "enter_admin_pw": "🔐 Введите пароль администратора:",
        "wrong_admin_pw": "❌ Неверный пароль.",
        "admin_title": "🔐 <b>Панель администратора</b>\n\nВыберите действие:",
        "sn_list_title": "📋 <b>Список SN (все записи о ремонте)</b>\n\n",
        "sn_list_empty": "📭 Записей о ремонте нет.",
        "not_configured": "⚠️ Таблица сервисного центра не настроена.",
        "contact_cs": "💬 Поддержка",
        "loading_err": "❌ Ошибка запроса. Попробуйте позже.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"].get(key, key))


def _agent_url(prefill: str) -> str:
    import urllib.parse
    return f"https://t.me/{settings.human_agent_username}?text={urllib.parse.quote(prefill)}"


# ── 主菜单 ───────────────────────────────────────────────

@router.callback_query(ServiceCenterCallback.filter(F.action == "menu"))
async def on_sc_menu(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if state:
        await state.clear()
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=service_center_menu_keyboard(lang, settings.service_center_tg_link),
    )
    await callback.answer()


# ── 服务中心说明 ─────────────────────────────────────────

@router.callback_query(ServiceCenterCallback.filter(F.action == "info"))
async def on_sc_info(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_menu", lang):
        builder.row(*row)
    await callback.message.edit_text(_t(lang, "info_text"), reply_markup=builder.as_markup())
    await callback.answer()


# ── 服务中心链接（无配置时的回退） ────────────────────────

@router.callback_query(ServiceCenterCallback.filter(F.action == "link"))
async def on_sc_link(callback: CallbackQuery, lang: str = "zh") -> None:
    link = settings.service_center_tg_link
    if link and not link.endswith("placeholder_service"):
        await callback.answer(link, show_alert=True)
    else:
        await callback.answer("🔗 链接暂未配置", show_alert=True)


# ── 设备检修查询 FSM ─────────────────────────────────────

@router.callback_query(ServiceCenterCallback.filter(F.action == "repair"))
async def on_sc_repair_enter(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message or not state:
        return
    if not settings.service_center_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return
    await state.set_state(ServiceCenterStates.awaiting_cdek_no)
    await state.update_data(lang=lang)
    await callback.message.edit_text(_t(lang, "enter_cdek"))
    await callback.answer()


@router.message(ServiceCenterStates.awaiting_cdek_no)
async def on_cdek_no_input(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not state:
        return
    cdek_no = (message.text or "").strip()
    await state.clear()

    try:
        record = await get_repair_status(cdek_no)
    except Exception as e:
        logger.error("get_repair_status failed: %s", e)
        await message.answer(_t(lang, "loading_err"))
        return

    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_menu", lang):
        builder.row(*row)

    if not record:
        prefill = {"zh": f"你好，我查询单号 {cdek_no} 未找到记录", "en": f"Hi, tracking {cdek_no} not found", "ru": f"Привет, трек {cdek_no} не найден"}.get(lang, f"Track {cdek_no} not found")
        builder.row(InlineKeyboardButton(text=_t(lang, "contact_cs"), url=_agent_url(prefill)))
        await message.answer(
            _t(lang, "cdek_not_found").format(cdek_no=cdek_no),
            reply_markup=builder.as_markup(),
        )
        return

    # 注册状态监听（记录语言用于推送通知）
    user_id = message.from_user.id if message.from_user else 0
    if user_id:
        await register_watcher(cdek_no, user_id, lang)

    cdek_out_line = ""
    if record.cdek_out:
        cdek_out_line = _t(lang, "cdek_out_line").format(cdek_out=record.cdek_out)

    text = _t(lang, "cdek_result").format(
        cdek_in=record.cdek_in,
        model=record.model or "-",
        sn=record.sn or "-",
        emoji=record.status_emoji(),
        status=record.status or "-",
        cdek_out_line=cdek_out_line,
    )
    await message.answer(text, reply_markup=builder.as_markup())


# ── 管理员入口（文本密码触发，无按钮）────────────────────────

@router.message(StateFilter(default_state), F.text == settings.service_admin_password)
async def on_admin_password(
    message: Message,
    lang: str = "zh",
) -> None:
    await message.answer(_t(lang, "admin_title"), reply_markup=service_center_admin_keyboard(lang))


@router.callback_query(ServiceCenterCallback.filter(F.action == "admin_menu"))
async def on_admin_notify_info(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    info = {
        "zh": "📩 <b>维修完成通知</b>\n\n当管理员在 Google 表格中填写「回寄CDEK单号」时，系统将自动通知对应客户。\n\n无需手动操作，状态监听后台每 5 分钟轮询一次。",
        "en": "📩 <b>Repair Completion Notifications</b>\n\nWhen the admin fills in the return CDEK number in the Google Sheet, the customer is notified automatically.\n\nNo manual action needed — the monitor checks every 5 minutes.",
        "ru": "📩 <b>Уведомление о завершении</b>\n\nКогда администратор заполнит номер CDEK возврата в таблице, клиент получит уведомление автоматически.\n\nМониторинг каждые 5 минут.",
    }.get(lang, "")
    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_admin", lang):
        builder.row(*row)
    await callback.message.edit_text(info, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(ServiceCenterCallback.filter(F.action == "sn_list"))
async def on_sn_list(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    try:
        records = await get_all_records()
    except Exception as e:
        logger.error("get_all_records failed: %s", e)
        await callback.answer(_t(lang, "loading_err"), show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_admin", lang):
        builder.row(*row)

    if not records:
        await callback.message.edit_text(
            _t(lang, "sn_list_empty"),
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    lines = [_t(lang, "sn_list_title")]
    for r in records[:30]:  # 最多展示 30 条防超长
        lines.append(
            f"<code>{r.cdek_in}</code>  {r.model or '-'}  "
            f"SN:{r.sn or '-'}  {r.status_emoji()} {r.status or '-'}"
        )
    if len(records) > 30:
        lines.append(f"\n... 共 {len(records)} 条，仅展示前 30 条")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n…"
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()



async def show_sc_menu(callback: CallbackQuery, lang: str) -> None:
    """供 menu.py NavCallback 路由调用，显示服务中心菜单."""
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=service_center_menu_keyboard(lang, settings.service_center_tg_link),
    )


async def show_sc_admin(callback: CallbackQuery, lang: str) -> None:
    """供 menu.py NavCallback 路由调用，显示服务中心管理后台."""
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "admin_title"),
        reply_markup=service_center_admin_keyboard(lang),
    )
