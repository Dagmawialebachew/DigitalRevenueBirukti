import html
import logging
import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db import db
from services.payout_engine import (
    record_verified_payout,
    get_creator_payout_summary,
    settle_unsettled_payouts,
)
from services.deliverer import deliver_workout_program
from keyboards.admin_kb import (
    get_admin_home_keyboard,
    get_admin_reply_menu,
    get_admin_review_keyboard,
    get_pending_queue_markup,
)
from keyboards.user_kb import get_support_keyboard
from utils.tg_helpers import safe_answer, safe_delete, format_plan_name, format_age_display

router = Router()
logger = logging.getLogger(__name__)

PAY_PER_PAGE = 5

_PRODUCT_DETAILS_MAP = {
    "BF-F-BC-3X": (
        "👩 Female (Women)", "3 Days / Week", "🍑 ዳሌና መቀመጫ ማውጣት",
        "Glute-focused lower body sculpting + waist shaping + core stability",
    ),
    "BF-F-BC-4X": (
        "👩 Female (Women)", "4 Days / Week", "🍑 ዳሌና መቀመጫ ማውጣት",
        "2x Glute/Lower focus + Upper tone + Full-body sculpt for balanced curves",
    ),
    "BF-F-FL-3X": (
        "👩 Female (Women)", "3 Days / Week", "🔥 ቦርጭና ስብ መቀነስ",
        "Calorie-deficit strength training + belly fat burn + cardio guidelines",
    ),
    "BF-F-FL-4X": (
        "👩 Female (Women)", "4 Days / Week", "🔥 ቦርጭና ስብ መቀነስ",
        "High-efficiency 4-day fat loss split + core conditioning + nutrition deficit",
    ),
    "BF-M-MG-3X": (
        "👨 Male (Men)", "3 Days / Week", "💪 ጡንቻ ግንባታ",
        "3-day lean hypertrophy split + progressive overload + calorie surplus guide",
    ),
    "BF-M-MG-4X": (
        "👨 Male (Men)", "4 Days / Week", "💪 ጡንቻ ግንባታ",
        "Lower Body, Chest & Back, Shoulders & Arms, Full Body + 1-2 RIR tracking",
    ),
    "BF-M-FL-3X": (
        "👨 Male (Men)", "3 Days / Week", "🔥 ቦርጭና ስብ መቀነስ",
        "Preserve strength while cutting belly fat + cardio & Ethiopian food swaps",
    ),
    "BF-M-FL-4X": (
        "👨 Male (Men)", "4 Days / Week", "🔥 ቦርጭና ስብ መቀነስ",
        "4-day shred protocol + lean calorie/protein targets + recovery tracking",
    ),
}


class AdminReplyFSM(StatesGroup):
    awaiting_reply = State()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


async def _send_reply_to_user(bot: Bot, admin_msg: Message, target_user_id: int) -> bool:
    """Deliver text, photo, document, or voice reply cleanly from Coach Biruktawit to a user."""
    header = "💬 <b>ከአሰልጣኝ ብሩክታዊት የተላከ መልዕክት፦</b>\n\n"
    support_kb = get_support_keyboard()

    try:
        if admin_msg.text:
            body = f"{header}{html.escape(admin_msg.text)}"
            await bot.send_message(target_user_id, body, parse_mode="HTML", reply_markup=support_kb)
        elif admin_msg.photo:
            cap = f"{header}{html.escape(admin_msg.caption)}" if admin_msg.caption else header.strip()
            await bot.send_photo(target_user_id, photo=admin_msg.photo[-1].file_id, caption=cap, parse_mode="HTML", reply_markup=support_kb)
        elif admin_msg.document:
            cap = f"{header}{html.escape(admin_msg.caption)}" if admin_msg.caption else header.strip()
            await bot.send_document(target_user_id, document=admin_msg.document.file_id, caption=cap, parse_mode="HTML", reply_markup=support_kb)
        elif admin_msg.voice:
            await bot.send_message(target_user_id, header.strip(), parse_mode="HTML")
            await bot.send_voice(target_user_id, voice=admin_msg.voice.file_id, reply_markup=support_kb)
        else:
            await bot.copy_message(chat_id=target_user_id, from_chat_id=admin_msg.chat.id, message_id=admin_msg.message_id)
        return True
    except Exception as e:
        logger.warning(f"Failed to deliver admin reply to {target_user_id}: {e}")
        return False


async def render_admin_dashboard() -> str:
    """Compact daily snapshot (users, sales, gross & today revenue, milestone, pending action)."""
    s = await db.get_admin_dashboard_stats()

    paid_sales = s["paid_sales"]
    pending_receipts = s["pending_receipts"]
    progress_blocks = min(6, int((min(paid_sales, 150) / 150) * 6)) if paid_sales > 0 else 0
    milestone_bar = "▰" * progress_blocks + "▱" * (6 - progress_blocks)

    status_emoji = "🚨" if pending_receipts > 0 else "✅"
    status_text = f"ACTION REQUIRED ({pending_receipts} slips)" if pending_receipts > 0 else "Operational"
    now_str = datetime.now().strftime("%H:%M:%S")

    return (
        "👑 <b>BIRUKTAWIT // DAILY COMMAND</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Users:</b> <code>{s['total_users']:,}</code> <i>(+{s['today_users']} today)</i>\n"
        f"💳 <b>Paid Sales:</b> <code>{paid_sales:,}</code> <i>(+{s['today_sales']} today)</i>\n"
        f"💰 <b>Gross Revenue:</b> <code>{s['gross_revenue']:,.0f} ETB</code>\n"
        f"📅 <b>Today Revenue:</b> <code>{s['today_revenue']:,.0f} ETB</code>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🚀 <b>70/30 Milestone:</b> {milestone_bar} <code>{min(paid_sales, 150)}/150</code>\n"
        f"⏳ <b>Pending Payments:</b> <code>{pending_receipts}</code> slips | <code>{s['pending_checkouts']}</code> checkout\n"
        f"{status_emoji} <b>Status:</b> {status_text}  |  ⏱ <i>{now_str}</i>"
    )


def _build_products_inline_keyboard(rows: list):
    builder = InlineKeyboardBuilder()
    for r in rows:
        sku = r["sku"]
        plan_name = format_plan_name(sku, r.get("title"))
        builder.button(text=f"📘 {plan_name}", callback_data=f"adm_prod:{sku}")
    builder.adjust(1)
    return builder.as_markup()


async def _safe_edit_dashboard(callback: CallbackQuery, text: str, markup=None, toast: str | None = None):
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup or get_admin_home_keyboard())
        await safe_answer(callback, toast)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await safe_answer(callback, "Already up to date!")
        else:
            raise


# ---------------------------------------------------------
# Admin Home Command: /admin
# ---------------------------------------------------------
@router.message(Command("admin"))
async def handle_admin_command(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    dashboard_text = await render_admin_dashboard()
    await message.answer("📋 <b>Admin Menu</b>", parse_mode="HTML", reply_markup=get_admin_reply_menu())
    await message.answer(dashboard_text, parse_mode="HTML", reply_markup=get_admin_home_keyboard())


@router.message(Command("cancel"))
async def handle_admin_cancel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("✅ Cancelled active admin action.", reply_markup=get_admin_reply_menu())


# ---------------------------------------------------------
# Pending Payment Ledger & Receipt Inspection (CoachHilawe Flow)
# ---------------------------------------------------------
@router.message(F.text == "⏳ Pending Payment", F.from_user.id.in_(settings.admin_ids_list))
@router.callback_query(F.data.startswith("paypage:"), F.from_user.id.in_(settings.admin_ids_list))
async def view_payment_ledger(event: Message | CallbackQuery):
    page = 0
    if isinstance(event, CallbackQuery):
        await safe_answer(event)
        page = int(event.data.split(":")[1])

    offset = page * PAY_PER_PAGE
    async with db.pool.acquire() as conn:
        pending_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE status = 'PENDING' AND receipt_file_id IS NOT NULL;"
        )
        rows = await conn.fetch(
            """
            SELECT o.order_id, o.amount_etb, o.created_at, a.full_name, a.username
            FROM orders o
            JOIN athletes a ON o.athlete_id = a.telegram_id
            WHERE o.status = 'PENDING' AND o.receipt_file_id IS NOT NULL
            ORDER BY o.created_at ASC
            LIMIT $1 OFFSET $2;
            """,
            PAY_PER_PAGE,
            offset,
        )

    orders = [dict(r) for r in rows]
    total_pages = max(1, (pending_count + PAY_PER_PAGE - 1) // PAY_PER_PAGE)

    header = (
        "💳 <b>PENDING PAYMENT QUEUE</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"Total Pending Slips: <code>{pending_count}</code>\n"
        "Select a record to inspect receipt:"
    )

    if isinstance(event, Message):
        if pending_count == 0:
            await event.answer("✅ <b>Queue Clear.</b> No pending receipts waiting.", parse_mode="HTML")
            return
        await event.answer(header, parse_mode="HTML", reply_markup=get_pending_queue_markup(orders, page, total_pages))
    else:
        if pending_count == 0:
            await event.message.edit_text("✅ <b>Queue Clear.</b> No pending receipts waiting.", parse_mode="HTML")
            return
        await event.message.edit_text(header, parse_mode="HTML", reply_markup=get_pending_queue_markup(orders, page, total_pages))


@router.callback_query(F.data == "noop_page", F.from_user.id.in_(settings.admin_ids_list))
async def handle_noop_page(callback: CallbackQuery):
    await safe_answer(callback)


@router.callback_query(F.data.startswith("adm_inspect:"), F.from_user.id.in_(settings.admin_ids_list))
async def inspect_single_payment(callback: CallbackQuery, bot: Bot):
    await safe_answer(callback)
    order_id = callback.data.split(":", 1)[1]

    async with db.pool.acquire() as conn:
        pay = await conn.fetchrow(
            """
            SELECT o.*, a.full_name, a.username, a.gender
            FROM orders o
            JOIN athletes a ON o.athlete_id = a.telegram_id
            WHERE o.order_id = $1;
            """,
            order_id,
        )

    if not pay or not pay.get("receipt_file_id"):
        await callback.message.answer("❌ Receipt record not found or already cleared.")
        return

    gender_display = "👩 Female" if pay.get("gender") == "FEMALE" else "👨 Male"
    uname = f"@{html.escape(pay['username'])}" if pay.get("username") else "No Username"
    plan_name = html.escape(format_plan_name(pay["sku"]))
    date_str = pay["created_at"].strftime("%Y-%m-%d %H:%M") if pay.get("created_at") else "N/A"

    ledger_detail = (
        f"📑 <b>TRANSACTION DETAILS // {html.escape(order_id)}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Client:</b> {html.escape(pay['full_name'] or 'Member')} ({uname})\n"
        f"🧬 <b>Gender:</b> {gender_display}\n"
        f"📦 <b>Plan:</b> {plan_name}\n"
        f"💰 <b>Amount:</b> <code>{pay['amount_etb']} ETB</code>\n"
        f"📅 <b>Date:</b> <code>{date_str}</code>\n"
        "━━━━━━━━━━━━━━━━"
    )

    await safe_delete(callback.message)
    review_kb = get_admin_review_keyboard(order_id)
    file_id = pay["receipt_file_id"]

    try:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=file_id,
            caption=ledger_detail,
            reply_markup=review_kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=file_id,
            caption=ledger_detail,
            reply_markup=review_kb,
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# Products Catalog & Global Broadcast (Coming Soon)
# ---------------------------------------------------------
@router.message(F.text == "📦 Products", F.from_user.id.in_(settings.admin_ids_list))
async def handle_admin_btn_products(message: Message):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT sku, title FROM workout_catalog WHERE is_active = TRUE ORDER BY sku;")

    if not rows:
        await message.answer("📦 No active products found.")
        return

    text = (
        "📦 <b>ACTIVE 8-WEEK PRODUCTS</b>\n\n"
        "Tap any product below to inspect what it contains 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=_build_products_inline_keyboard(rows))


@router.callback_query(F.data.startswith("adm_prod:"))
async def callback_view_product_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized.", show_alert=True)
        return
    await safe_answer(callback)

    sku = callback.data.split(":", 1)[1]
    plan_name = html.escape(format_plan_name(sku))
    audience, freq, goal_amh, focus_desc = _PRODUCT_DETAILS_MAP.get(
        sku,
        ("All Members", "3-4 Days / Week", "Custom Fitness Plan", "Structured 8-week gym protocol"),
    )

    detail_text = (
        f"📘 <b>{plan_name}</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Audience:</b> {html.escape(audience)}\n"
        f"📅 <b>Schedule:</b> {html.escape(freq)}\n"
        f"🎯 <b>Goal:</b> {html.escape(goal_amh)}\n"
        f"💰 <b>Price:</b> <code>{settings.DEFAULT_PRICE_ETB} ETB</code>\n\n"
        "<b>What This 20-Page Manual Contains:</b>\n"
        f"• {html.escape(focus_desc)}\n"
        "• Chapter 1: Foundation Rules &amp; Form Over Weight\n"
        "• Chapter 2: Warm-up, Mobility, Daily Workouts + CLICK HERE Video Demos + 1-2 RIR\n"
        "• Chapter 3: Calorie &amp; Protein Math + Ethiopian Smart Food Swaps + Recovery &amp; Sunday Tracker"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back to Products", callback_data="adm_products_list")
    await callback.message.edit_text(detail_text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "adm_products_list")
async def callback_products_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized.", show_alert=True)
        return
    await safe_answer(callback)

    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT sku, title FROM workout_catalog WHERE is_active = TRUE ORDER BY sku;")

    text = (
        "📦 <b>ACTIVE 8-WEEK PRODUCTS</b>\n\n"
        "Tap any product below to inspect what it contains 👇"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_build_products_inline_keyboard(rows))


@router.message(F.text == "📢 Global Broadcast", F.from_user.id.in_(settings.admin_ids_list))
async def handle_admin_btn_broadcast(message: Message):
    await message.answer(
        "🚧 <b>Global Broadcast</b> is coming soon!",
        parse_mode="HTML",
        reply_markup=get_admin_reply_menu(),
    )


# ---------------------------------------------------------
# Effortless Admin Reply #1 & #2: Button + Swipe-to-Reply
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("adm_reply:"))
async def handle_admin_quick_reply_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized.", show_alert=True)
        return

    await safe_answer(callback)
    target_user_id = int(callback.data.split(":")[1])
    await state.set_state(AdminReplyFSM.awaiting_reply)
    await state.update_data(target_user_id=target_user_id)

    await callback.message.answer(
        f"✍️ <b>Replying to User ID:</b> <code>{target_user_id}</code>\n"
        "Send your text, photo, or voice message below (or send /cancel to abort).",
        parse_mode="HTML",
    )


@router.message(AdminReplyFSM.awaiting_reply)
async def handle_admin_quick_reply_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    if not target_user_id:
        await message.answer("❌ Target user expired. Try clicking Quick Reply again.")
        return

    ok = await _send_reply_to_user(bot, message, int(target_user_id))
    if ok:
        await message.answer(f"✅ Reply sent to <code>{target_user_id}</code>.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Could not deliver reply to <code>{target_user_id}</code> (user may have blocked the bot).", parse_mode="HTML")


@router.message(F.from_user.id.in_(settings.admin_ids_list), F.reply_to_message)
async def handle_admin_swipe_reply(message: Message, bot: Bot):
    replied = message.reply_to_message
    source_text = (replied.text or replied.caption or "")
    match = re.search(r"ID:\s*(\d+)", source_text)
    if not match:
        return

    target_user_id = int(match.group(1))
    ok = await _send_reply_to_user(bot, message, target_user_id)
    if ok:
        await message.answer(f"✅ Reply delivered to <code>{target_user_id}</code>.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Delivery failed for <code>{target_user_id}</code> (user may have blocked the bot).", parse_mode="HTML")


# ---------------------------------------------------------
# Payment Slip Approve / Reject Callbacks
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("adm_app:"))
async def handle_admin_approve(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized: Admin privileges required.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    order = await db.get_order(order_id)
    if not order:
        await safe_answer(callback, "Order not found in database!", show_alert=True)
        return

    if order["status"] in ("VERIFIED", "DELIVERED"):
        await safe_answer(callback, "Order already verified and delivered!", show_alert=True)
        return

    payout_info = await record_verified_payout(order_id, order["amount_etb"])
    if payout_info.get("already_processed"):
        await safe_answer(callback, "Order was already processed by another admin.", show_alert=True)
        return

    await safe_answer(callback, "Order verified! Sending PDF...")

    athlete_id = order["athlete_id"]
    await deliver_workout_program(bot, athlete_id, order_id)
    await db.update_athlete_field(athlete_id, "onboarding_state", "ACTIVE_MEMBER")

    actor_name = html.escape(callback.from_user.first_name or callback.from_user.full_name or "Admin")
    base_caption = html.escape(callback.message.caption or "")
    status_update = (
        f"{base_caption}\n\n"
        f"✅ <b>APPROVED by {actor_name}</b>\n"
        f"📊 Sale #: <code>{payout_info['sale_number']}</code> ({html.escape(payout_info['tier'])})\n"
        f"👩‍💼 Biruktawit Share: <code>{payout_info['creator_share']} ETB</code>\n"
        f"💻 Platform Share: <code>{payout_info['platform_share']} ETB</code>"
    )
    try:
        await callback.message.edit_caption(caption=status_update, parse_mode="HTML", reply_markup=None)
    except Exception as e:
        logger.warning(f"Failed to edit approved caption cleanly: {e}")


@router.callback_query(F.data.startswith("adm_rej:"))
async def handle_admin_reject(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized: Admin privileges required.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    order = await db.get_order(order_id)
    if order:
        async with db.pool.acquire() as conn:
            updated = await conn.fetchrow(
                "UPDATE orders SET status = 'REJECTED' WHERE order_id = $1 AND status = 'PENDING' RETURNING order_id;",
                order_id,
            )
        if not updated:
            await safe_answer(callback, "Order is no longer pending.", show_alert=True)
            return

        await safe_answer(callback, "Receipt rejected.")

        athlete = await db.get_athlete(order["athlete_id"])
        is_female = athlete and athlete.get("gender") == "FEMALE"
        support_ref = f"@{html.escape(settings.SUPPORT_BOT_USERNAME)}"
        if is_female:
            reject_msg = (
                "ሰላም ቆንጆዬ! የላክሽው የክፍያ ደረሰኝ አልታየም ወይም ትክክል አይደለም።\n\n"
                f"እባክሽ ትክክለኛውን የባንክ ደረሰኝ Screenshot አድርገሽ እንደገና ላኪ፣ ወይም {support_ref} ላይ ጻፊልን።"
            )
        else:
            reject_msg = (
                "ሰላም ወንድሜ! የላክኸው የክፍያ ደረሰኝ አልታየም ወይም ትክክል አይደለም።\n\n"
                f"እባክህ ትክክለኛውን የባንክ ደረሰኝ Screenshot አድርገህ እንደገና ላክ፣ ወይም {support_ref} ላይ ጻፍልን።"
            )
        try:
            await bot.send_message(order["athlete_id"], reject_msg, parse_mode="HTML", reply_markup=get_support_keyboard())
        except Exception:
            pass
    else:
        await safe_answer(callback, "Order not found.", show_alert=True)

    actor_name = html.escape(callback.from_user.first_name or callback.from_user.full_name or "Admin")
    base_caption = html.escape(callback.message.caption or "")
    try:
        await callback.message.edit_caption(
            caption=f"{base_caption}\n\n❌ <b>REJECTED by {actor_name}</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"Failed to edit rejected caption: {e}")


# ---------------------------------------------------------
# Inline Refresh & Admin Text Commands (/payouts, /funnel, /users, /user, /settle)
# ---------------------------------------------------------
@router.callback_query(F.data == "adm_home")
async def callback_admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized.", show_alert=True)
        return
    dashboard_text = await render_admin_dashboard()
    await _safe_edit_dashboard(callback, dashboard_text)


@router.callback_query(F.data == "adm_refresh_stats")
async def callback_refresh_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "Unauthorized.", show_alert=True)
        return
    dashboard_text = await render_admin_dashboard()
    await _safe_edit_dashboard(callback, dashboard_text, toast="Stats updated! ⚡️")


def _format_payout_report(summary: dict) -> str:
    handle = html.escape(settings.CREATOR_HANDLE.upper())
    report = (
        f"📊 <b>BIRUKTAWIT FIKRE ({handle}) // REVENUE &amp; SPLIT LEDGER</b>\n\n"
        f"• Total Verified Sales: <code>{summary['total_sales']}</code>\n"
        f"• Total Gross Revenue: <code>{summary['total_gross_etb']:,.2f} ETB</code>\n"
        f"• Biruktawit Total Earnings: <code>{summary['total_creator_earnings_etb']:,.2f} ETB</code>\n"
        f"• Platform Total Earnings: <code>{summary['total_platform_earnings_etb']:,.2f} ETB</code>\n"
        f"• Unsettled Creator Balance: <code>{summary['unsettled_creator_balance_etb']:,.2f} ETB</code>\n\n"
        "📈 <b>Tier Breakdown:</b>\n"
        f"  - Tier 1 (60%): <code>{summary['tier_1_sales_count']} sales</code>\n"
        f"  - Tier 2 (70%): <code>{summary['tier_2_sales_count']} sales</code>\n"
        f"🎯 <b>Active Tier:</b> <code>{html.escape(summary['current_tier'])}</code>\n"
    )
    if summary["sales_to_next_tier"] > 0:
        report += f"⚡ Sales remaining until permanent 70% split: <code>{summary['sales_to_next_tier']}</code>"
    else:
        report += "🚀 <b>PERMANENT 70% CREATOR TIER ACTIVE</b>"
    return report


@router.message(Command("payouts"))
async def handle_payouts_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    summary = await get_creator_payout_summary()
    await message.answer(_format_payout_report(summary), parse_mode="HTML", reply_markup=get_admin_home_keyboard())


@router.message(Command("funnel"))
async def handle_funnel_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = await render_funnel_report()
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_home_keyboard())


@router.message(Command("users"))
async def handle_users_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = await render_users_report()
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_home_keyboard())


@router.message(Command("user"))
async def handle_user_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Usage: <code>/user &lt;telegram_id_or_username&gt;</code>", parse_mode="HTML")
        return

    query = parts[1]
    athlete = await db.get_athlete_by_id_or_username(query)
    if not athlete:
        await message.answer(f"❌ Member <code>{html.escape(query)}</code> not found in database.", parse_mode="HTML")
        return

    t_id = athlete["telegram_id"]
    checkins = await db.get_athlete_checkins(t_id)
    orders = await db.get_athlete_order_history(t_id)

    safe_name = html.escape(athlete["full_name"] or "Unknown")
    safe_uname = f"@{html.escape(athlete['username'])}" if athlete.get("username") else "N/A"

    info = (
        f"👤 <b>MEMBER DOSSIER // {safe_name}</b>\n\n"
        f"• Telegram ID: <code>{t_id}</code>\n"
        f"• Username: {safe_uname}\n"
        f"• Gender: <code>{html.escape(str(athlete.get('gender') or 'N/A'))}</code>\n"
        f"• Age: <code>{html.escape(format_age_display(athlete))}</code> | Weight: <code>{athlete.get('weight_kg') or 'N/A'} kg</code>\n"
        f"• Goal: <code>{html.escape(str(athlete.get('primary_goal') or 'N/A'))}</code>\n"
        f"• Split: <code>{athlete.get('days_per_week') or 'N/A'} days/week</code>\n"
        f"• 📍 <b>Current Bot Progress:</b> <code>{html.escape(str(athlete.get('onboarding_state')))}</code>\n"
        f"• Last Active: <code>{html.escape(str(athlete.get('last_interaction')))}</code>\n\n"
        f"📦 <b>Orders ({len(orders)}):</b>\n"
    )
    for o in orders[:3]:
        info += (
            f"  - <code>{html.escape(o['order_id'])}</code>: {html.escape(format_plan_name(o['sku']))} "
            f"({o['amount_etb']} ETB) [{html.escape(o['status'])}]\n"
        )

    info += f"\n📝 <b>Weekly Check-ins Logged:</b> <code>{len(checkins)} check-ins</code>\n"
    for c in checkins[-4:]:
        info += f"  - Week {c['week_number']}: <code>{c['weight_kg']} kg</code> ({c['workouts_completed']} workouts)\n"

    await message.answer(info, parse_mode="HTML", reply_markup=get_admin_home_keyboard())


async def render_users_report() -> str:
    athletes = await db.get_recent_athletes(limit=15)
    if not athletes:
        return "👥 <b>NO RECENT MEMBERS FOUND</b>"

    lines = ["👥 <b>RECENT MEMBERS &amp; CURRENT BOT PROGRESS</b>\n"]
    for i, a in enumerate(athletes, 1):
        safe_name = html.escape(a["full_name"] or "Unknown")
        uname = f"@{html.escape(a['username'])}" if a.get("username") else "No username"
        state = html.escape(a.get("onboarding_state") or "START")
        gender = "👩" if a.get("gender") == "FEMALE" else ("👨" if a.get("gender") == "MALE" else "❓")
        order_st = a.get("latest_order_status")
        status_badge = f" [Order: {html.escape(order_st)}]" if order_st else ""

        lines.append(f"{i}. {gender} <b>{safe_name}</b> ({uname})")
        lines.append(f"   🆔 <code>{a['telegram_id']}</code> | 📍 State: <code>{state}</code>{status_badge}")
        lines.append(f"   🎯 Goal: <code>{html.escape(str(a.get('primary_goal') or 'Not set'))}</code> | ⚖️ <code>{a.get('weight_kg') or 'N/A'} kg</code>\n")

    lines.append("💡 <i>Tip: Send <code>/user &lt;id&gt;</code> to inspect a member's journey and check-ins.</i>")
    return "\n".join(lines)


async def render_funnel_report() -> str:
    m = await db.get_funnel_metrics()
    total = m["total_athletes"]
    sc = m["state_counts"]
    delivered = m["delivered_orders"]
    pending = m["pending_receipts"]
    rev = m["total_revenue_etb"]

    conv_rate = (delivered / total * 100) if total > 0 else 0.0

    return (
        "📈 <b>CONVERSION FUNNEL &amp; MEMBER ANALYTICS</b>\n\n"
        f"👥 <b>Total Registered Members:</b> <code>{total}</code>\n\n"
        "🚶‍♂️ <b>Step-by-Step Funnel Progression:</b>\n"
        f"• Started Funnel: <code>{sc.get('START', 0)}</code>\n"
        f"• Gender &amp; Age Set: <code>{sc.get('GENDER_SET', 0) + sc.get('AGE_SET', 0)}</code>\n"
        f"• Weight Profiled: <code>{sc.get('WEIGHT_SET', 0)}</code>\n"
        f"• Goal Selected: <code>{sc.get('GOAL_SET', 0)}</code>\n"
        f"• Schedule Chosen: <code>{sc.get('SPLIT_SET', 0)}</code>\n"
        f"• Profile Card Generated: <code>{sc.get('DIAGNOSTIC_READY', 0)}</code>\n"
        f"• Checkout Pitch Viewed: <code>{sc.get('CHECKOUT_PITCHED', 0)}</code>\n"
        f"• Receipts Uploaded: <code>{sc.get('RECEIPT_SUBMITTED', 0)}</code>\n"
        f"• Active Paid Members: <code>{sc.get('ACTIVE_MEMBER', 0) + delivered}</code>\n\n"
        "💰 <b>Performance Summary:</b>\n"
        f"• Conversion Rate (Visit to Paid): <code>{conv_rate:.1f}%</code>\n"
        f"• Total Paid Revenue: <code>{rev:,.2f} ETB</code>\n"
        f"• Pending Review Queue: <code>{pending} orders</code>"
    )


@router.message(Command("settle"))
async def handle_settle_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    result = await settle_unsettled_payouts()
    if result["settled_count"] == 0:
        await message.answer("ℹ️ No unsettled payouts to settle at this time.")
        return

    batch_preview = ", ".join(result["payout_ids"][:5])
    if len(result["payout_ids"]) > 5:
        batch_preview += "..."

    text = (
        "✅ <b>CREATOR PAYOUT SETTLEMENT COMPLETED</b>\n\n"
        f"• Settled Records: <code>{result['settled_count']}</code>\n"
        f"• Total Transferred to Biruktawit: <code>{result['total_settled_etb']:,.2f} ETB</code>\n"
        f"• Batch Payouts: <code>{html.escape(batch_preview)}</code>\n\n"
        "All corresponding records in <code>payout_ledger</code> are now marked as <code>SETTLED</code>."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_home_keyboard())
