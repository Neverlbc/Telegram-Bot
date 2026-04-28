"""A-BF 俄罗斯服务中心.

功能：
1. 服务中心说明（静态文本）
2. 服务中心 TG 入口链接
3. 设备检修查询（输入 CDEK 单号 → 查 Google 表 → 返回状态 + 订阅状态变更）
4. 管理员入口（发送配置文件中的 SERVICE_ADMIN_PASSWORD → 后台隐藏菜单）
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import ServiceCenterCallback
from bot.keyboards.inline import (
    nav_buttons,
    service_center_admin_keyboard,
    service_center_menu_keyboard,
)
from bot.services.hidden_access import (
    MENU_SERVICE_ADMIN,
    clear_state_keep_hidden_access,
    has_hidden_access,
)
from bot.services.service_center_sheet import (
    get_all_records,
    get_repair_status,
    get_repair_status_by_sn,
    register_watcher,
)
from bot.services.sn_sheet import search_sn
from bot.states.service_center import ServiceCenterStates

logger = logging.getLogger(__name__)
router = Router(name="service_center")

# ── 多语言文案 ──────────────────────────────────────────

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "menu_title": (
            "🛠️ A-BF俄罗斯服务中心\n\n"
            "📋 服务中心说明介绍（含工作时间）\n\n"
            "🔗 服务中心入口链接（可订阅）\n\n"
            "🔍 设备检修查询"
        ),
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
        "enter_cdek": "🔧 <b>设备检修查询</b>\n\n请输入您寄件的 CDEK 单号，或设备序列号（SN）：",
        "cdek_not_found": "❓ 未找到 <code>{cdek_no}</code> 的记录。\n\n请确认 CDEK 单号或序列号是否正确，或联系客服：",
        "cdek_result": (
            "🔧 <b>检修状态查询结果</b>\n\n"
            "CDEK 单号：<code>{cdek_in}</code>\n"
            "设备型号：{model}\n"
            "序列号：{sn}\n"
            "检修状态：{emoji} {status}\n"
            "{cdek_out_line}"
            "{repair_summary_line}"
            "\n{notify_line}"
        ),
        "cdek_out_line": "回寄单号：<code>{cdek_out}</code>\n",
        "repair_summary_line": "维修报告：{summary}\n",
        "notify_done": "📦 您的设备已从服务中心寄回，请及时关注 CDEK 状态。",
        "notify_in_progress": (
            "您的设备正在处理中。由于服务中心工作量较大，可能会有所延迟。"
            "我们的工程师正在尽全力处理大量工单，努力尽快将设备归还给您。\n\n"
            "请耐心等待状态更新。如有紧急情况，请直接通过服务中心频道联系客服获取更多信息。"
        ),
        "notify_watch": "✅ 已订阅状态更新，有变更时将自动通知您。",
        "enter_admin_pw": "🔐 请输入管理员密码：",
        "wrong_admin_pw": "❌ 密码错误。",
        "access_expired": "🔐 管理员访问已过期，请重新输入访问码。",
        "admin_title": (
            "👁️ 您好，欢迎来到服务中心的隐藏菜单。\n\n"
            "当前可用功能：\n\n"
            "📋 维修记录列表 — 近期维修记录清单，方便快速查阅。\n"
            "🔍 查询设备序列号（S/N）— 验证设备是否来自我司。\n\n"
            "📱 维修完成通知 — 该功能需在数据库中配置终端用户手机号，暂未开放。\n\n"
            "如需其他协助，请直接联系 A-BF 服务中心管理团队。"
        ),
        "sn_list_title": "📋 <b>SN 表（全部检修记录）</b>\n\n",
        "sn_list_empty": "📭 暂无检修记录。",
        "not_configured": "⚠️ 服务中心 Google Sheet 未配置，请联系管理员。",
        "contact_cs": "💬 联系客服",
        "loading_err": "❌ 查询失败，请稍后重试。",
    },
    "en": {
        "menu_title": (
            "🛠️ A-BF Russia Service Center\n\n"
            "📋 Service Info &amp; Working Hours\n\n"
            "🔗 Service Channel Link (Subscribe)\n\n"
            "🔍 Repair Status Check"
        ),
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
        "enter_cdek": "🔧 <b>Device Repair Query</b>\n\nPlease enter your outgoing CDEK tracking number or device serial number (SN):",
        "cdek_not_found": "❓ No record found for <code>{cdek_no}</code>.\n\nPlease verify the CDEK number or SN, or contact support:",
        "cdek_result": (
            "🔧 <b>Repair Status</b>\n\n"
            "CDEK No.: <code>{cdek_in}</code>\n"
            "Model: {model}\n"
            "SN: {sn}\n"
            "Status: {emoji} {status}\n"
            "{cdek_out_line}"
            "{repair_summary_line}"
            "\n{notify_line}"
        ),
        "cdek_out_line": "Return CDEK No.: <code>{cdek_out}</code>\n",
        "repair_summary_line": "Repair Report: {summary}\n",
        "notify_done": "📦 Your device has been shipped back from the service center. Please track your CDEK status.",
        "notify_in_progress": (
            "Your device is currently being processed. Due to the high workload of our service center, there may be delays. "
            "Our engineers are doing their utmost to handle the large volume of requests, making every effort to return your device as quickly as possible.\n\n"
            "Please wait patiently for a status update. If your request is urgent, please contact customer support directly through the service center channel for more information."
        ),
        "notify_watch": "✅ Subscribed to updates — you'll be notified on any change.",
        "enter_admin_pw": "🔐 Enter admin password:",
        "wrong_admin_pw": "❌ Incorrect password.",
        "access_expired": "🔐 Admin access has expired. Please enter the access code again.",
        "admin_title": (
            "👁️ Welcome to the Service Center hidden menu.\n\n"
            "Available functions:\n\n"
            "📋 Repair Record List — recent repair case log, easy to browse.\n"
            "🔍 Search by Serial Number (S/N) — verify if the device comes from our company.\n\n"
            "📱 Repair Completion Notification — temporarily unavailable; requires client phone numbers "
            "configured in the database.\n\n"
            "For further assistance, please contact the A-BF Service Center management team directly."
        ),
        "sn_list_title": "📋 <b>SN List (all repair records)</b>\n\n",
        "sn_list_empty": "📭 No repair records found.",
        "not_configured": "⚠️ Service center sheet not configured. Contact admin.",
        "contact_cs": "💬 Contact Support",
        "loading_err": "❌ Query failed. Please try again later.",
    },
    "ru": {
        "menu_title": (
            "🛠️ A-BF Россия Сервисный центр\n\n"
            "📋 Описание сервиса и режим работы\n\n"
            "🔗 Ссылка на сервисный канал (подписаться)\n\n"
            "🔍 Проверить статус ремонта"
        ),
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
        "enter_cdek": "🔧 <b>Запрос ремонта</b>\n\nВведите номер CDEK вашего отправления или серийный номер устройства (SN):",
        "cdek_not_found": "❓ Запись для <code>{cdek_no}</code> не найдена.\n\nПроверьте номер CDEK или SN, или обратитесь в поддержку:",
        "cdek_result": (
            "🔧 <b>Статус ремонта</b>\n\n"
            "Номер CDEK: <code>{cdek_in}</code>\n"
            "Модель: {model}\n"
            "Серийный номер: {sn}\n"
            "Статус: {emoji} {status}\n"
            "{cdek_out_line}"
            "{repair_summary_line}"
            "\n{notify_line}"
        ),
        "cdek_out_line": "Номер CDEK для возврата: <code>{cdek_out}</code>\n",
        "repair_summary_line": "Отчёт о ремонте: {summary}\n",
        "notify_done": "📦 Ваше устройство отправлено из сервисного центра. Следите за статусом CDEK.",
        "notify_in_progress": (
            "Ваше устройство находится в обработке. В связи с высокой загрузкой нашего сервисного центра возможны задержки. "
            "Наши инженеры прилагают все усилия для обработки большого количества заявок и ремонта большого количества устройств, "
            "делая все возможное, чтобы как можно быстрее вернуть вам ваше устройство.\n\n"
            "Пожалуйста, терпеливо ждите обновления статуса. Если ваша заявка срочная, пожалуйста, свяжитесь со службой поддержки "
            "клиентов напрямую через канал сервисного центра для получения дополнительной информации."
        ),
        "notify_watch": "✅ Вы подписаны на обновления — уведомим при изменении.",
        "enter_admin_pw": "🔐 Введите пароль администратора:",
        "wrong_admin_pw": "❌ Неверный пароль.",
        "access_expired": "🔐 Доступ администратора истёк. Введите код доступа ещё раз.",
        "admin_title": (
            "👁️ Добро пожаловать в скрытое меню сервисного центра.\n\n"
            "Доступные функции:\n\n"
            "📋 Список ремонтов — перечень недавних обращений для быстрого просмотра.\n"
            "🔍 Поиск по серийному номеру (S/N) — проверка принадлежности прибора нашей компании.\n\n"
            "📱 Уведомление о готовности ремонта — услуга временно недоступна, требуется настройка базы "
            "номеров клиентов.\n\n"
            "По другим вопросам обращайтесь напрямую к команде управления сервисного центра A-BF."
        ),
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


async def _ensure_admin_access(
    callback: CallbackQuery,
    state: FSMContext | None,
    lang: str,
) -> bool:
    if not state:
        return False
    if await has_hidden_access(state, MENU_SERVICE_ADMIN):
        return True
    if callback.message:
        await callback.message.edit_text(
            _t(lang, "menu_title"),
            reply_markup=service_center_menu_keyboard(lang, settings.service_center_tg_link),
        )
    await callback.answer(_t(lang, "access_expired"), show_alert=True)
    return False


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
        await clear_state_keep_hidden_access(state)
    admin_unlocked = bool(state and await has_hidden_access(state, MENU_SERVICE_ADMIN))
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=service_center_menu_keyboard(
            lang,
            settings.service_center_tg_link,
            admin_unlocked=admin_unlocked,
        ),
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
    query = (message.text or "").strip()
    await clear_state_keep_hidden_access(state)

    try:
        record = await get_repair_status(query) or await get_repair_status_by_sn(query)
    except Exception as e:
        logger.error("get_repair_status failed: %s", e)
        await message.answer(_t(lang, "loading_err"))
        return

    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_menu", lang):
        builder.row(*row)

    if not record:
        prefill = {"zh": f"你好，我查询 {query} 未找到记录", "en": f"Hi, no record found for {query}", "ru": f"Привет, запись для {query} не найдена"}.get(lang, f"No record for {query}")
        builder.row(InlineKeyboardButton(text=_t(lang, "contact_cs"), url=_agent_url(prefill)))
        await message.answer(
            _t(lang, "cdek_not_found").format(cdek_no=query),
            reply_markup=builder.as_markup(),
        )
        return

    # 注册状态监听（使用记录中的实际 CDEK 单号作为 key）
    user_id = message.from_user.id if message.from_user else 0
    if user_id:
        await register_watcher(record.cdek_in, user_id, lang)

    cdek_out_line = ""
    repair_summary_line = ""
    is_done = record.status.strip().lower() == "done"
    if is_done:
        if record.cdek_out:
            cdek_out_line = _t(lang, "cdek_out_line").format(cdek_out=record.cdek_out)
        if record.repair_summary:
            repair_summary_line = _t(lang, "repair_summary_line").format(summary=record.repair_summary)

    status_lower = record.status.strip().lower()
    if is_done:
        notify_line = _t(lang, "notify_done")
    elif status_lower == "in progress":
        notify_line = _t(lang, "notify_in_progress")
    else:
        notify_line = _t(lang, "notify_watch")

    text = _t(lang, "cdek_result").format(
        cdek_in=record.cdek_in,
        model=record.model or "-",
        sn=record.sn or "-",
        emoji=record.status_emoji(),
        status=record.status or "-",
        cdek_out_line=cdek_out_line,
        repair_summary_line=repair_summary_line,
        notify_line=notify_line,
    )
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(ServiceCenterCallback.filter(F.action == "admin_menu"))
async def on_admin_notify_info(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if not await _ensure_admin_access(callback, state, lang):
        return
    info = {
        "zh": "📱 <b>维修完成通知</b>\n\n该功能需在数据库中配置终端用户手机号，暂未开放。",
        "en": (
            "📱 <b>Repair Completion Notification</b>\n\n"
            "Temporarily unavailable; requires client phone numbers configured in the database."
        ),
        "ru": (
            "📱 <b>Уведомление о готовности ремонта</b>\n\n"
            "Услуга временно недоступна, требуется настройка базы номеров клиентов."
        ),
    }.get(lang, "")
    builder = InlineKeyboardBuilder()
    for row in nav_buttons("sc_admin", lang):
        builder.row(*row)
    await callback.message.edit_text(info, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(ServiceCenterCallback.filter(F.action == "admin_home"))
async def on_admin_home(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if not await _ensure_admin_access(callback, state, lang):
        return
    await callback.message.edit_text(
        _t(lang, "admin_title"),
        reply_markup=service_center_admin_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(ServiceCenterCallback.filter(F.action == "sn_list"))
async def on_sn_list(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if not await _ensure_admin_access(callback, state, lang):
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



# ── 管理员 SN 搜索 ───────────────────────────────────────

@router.callback_query(ServiceCenterCallback.filter(F.action == "sn_search"))
async def on_sn_search_enter(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message or not state:
        return
    if not await _ensure_admin_access(callback, state, lang):
        return
    prompt = {
        "zh": "🔎 <b>查询设备序列号</b>\n\n请输入 SN 序列号（精确匹配）：",
        "en": "🔎 <b>Device SN Search</b>\n\nEnter the serial number (exact match):",
        "ru": "🔎 <b>Поиск серийного номера</b>\n\nВведите серийный номер (точное совпадение):",
    }.get(lang, "")
    await state.set_state(ServiceCenterStates.awaiting_sn_query)
    await callback.message.edit_text(prompt)
    await callback.answer()


@router.message(ServiceCenterStates.awaiting_sn_query)
async def on_sn_query_input(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not state:
        return
    if not await has_hidden_access(state, MENU_SERVICE_ADMIN):
        await state.clear()
        await message.answer(_t(lang, "access_expired"))
        return
    sn = (message.text or "").strip()
    await clear_state_keep_hidden_access(state)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text={"zh": "🔎 再查一个", "en": "🔎 Search again", "ru": "🔎 Ещё поиск"}.get(lang, "🔎"),
        callback_data=ServiceCenterCallback(action="sn_search").pack(),
    ))
    for row in nav_buttons("sc_admin", lang):
        builder.row(*row)

    try:
        results = await search_sn(sn)
    except Exception as e:
        logger.error("search_sn failed: %s", e)
        await message.answer(_t(lang, "loading_err"), reply_markup=builder.as_markup())
        return

    if not results:
        not_found = {
            "zh": f"❌ 服务中心数据库中未找到该序列号。\n\n很遗憾，我们无法确认该设备是否购自我司。请联系销售经理进行进一步核实。",
            "en": f"❌ The serial number was not found in the service center database.\n\nUnfortunately, we cannot confirm that this device was purchased from us. Please contact your sales manager for further verification.",
            "ru": f"❌ Серийный номер не найден в базе сервисного центра.\n\nК сожалению, мы не можем подтвердить, что этот прибор был приобретён у нас. Пожалуйста, свяжитесь с вашим менеджером по продажам для дальнейшей проверки.",
        }.get(lang, "")
        await message.answer(not_found, reply_markup=builder.as_markup())
        return

    lines = []
    for r in results:
        lines.append(r.format_text(lang))
        lines.append("")
    text = "\n".join(lines).strip()
    await message.answer(text, reply_markup=builder.as_markup())


async def show_sc_menu(callback: CallbackQuery, lang: str, admin_unlocked: bool = False) -> None:
    """供 menu.py NavCallback 路由调用，显示服务中心菜单."""
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=service_center_menu_keyboard(
            lang,
            settings.service_center_tg_link,
            admin_unlocked=admin_unlocked,
        ),
    )


async def show_sc_admin(callback: CallbackQuery, lang: str) -> None:
    """供 menu.py NavCallback 路由调用，显示服务中心管理后台."""
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "admin_title"),
        reply_markup=service_center_admin_keyboard(lang),
    )
