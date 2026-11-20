import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from config import settings
from database.db import db
from services.payout_engine import (
    record_verified_payout,
    get_creator_payout_summary,
    settle_unsettled_payouts
)
from services.deliverer import deliver_workout_program
from keyboards.admin_kb import (
    get_admin_home_keyboard,
    get_admin_catalog_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list

# ---------------------------------------------------------
# Admin Home Command: /admin
# ---------------------------------------------------------
@router.message(Command("admin"))
async def handle_admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = (
        "🛡️ **ADMIN CONTROL DASHBOARD // BIRUKTAWIT BOT**\n\n"
        "Welcome to the admin console. Manage payments, inspect payouts, "
        "and track the 60/40 ➔ 70/30 sales ledger below."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

# ---------------------------------------------------------
# Admin One-Click Approval Callback
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("adm_app:"))
async def handle_admin_approve(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized: Admin privileges required.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Order not found in database!", show_alert=True)
        return

    if order["status"] in ["VERIFIED", "DELIVERED"]:
        await callback.answer("Order already verified and delivered!", show_alert=True)
        return

    # 1. Record Revenue Split (60/40 -> 70/30 threshold rule)
    payout_info = await record_verified_payout(order_id, order["amount_etb"])

    # 2. Deliver the Workout PDF directly to the Athlete
    athlete_id = order["athlete_id"]
    await deliver_workout_program(bot, athlete_id, order_id)
    await db.update_athlete_field(athlete_id, "onboarding_state", "ACTIVE_MEMBER")

    # 3. Update Admin UI message in English
    status_update = (
        f"{callback.message.caption or ''}\n\n"
        f"✅ **APPROVED & DELIVERED**\n"
        f"📊 Sale #: `{payout_info['sale_number']}` ({payout_info['tier']})\n"
        f"👩‍💼 Biruktawit Share: `{payout_info['creator_share']} ETB`\n"
        f"💻 Platform Share: `{payout_info['platform_share']} ETB`"
    )
    await callback.message.edit_caption(caption=status_update, parse_mode="Markdown", reply_markup=None)
    await callback.answer("Order verified and PDF delivered successfully!")

# ---------------------------------------------------------
# Admin Reject Callback
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("adm_rej:"))
async def handle_admin_reject(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized: Admin privileges required.", show_alert=True)
        return

    order_id = callback.data.split(":")[1]
    order = await db.get_order(order_id)
    if order:
        async with db.pool.acquire() as conn:
            await conn.execute("UPDATE orders SET status = 'REJECTED' WHERE order_id = $1;", order_id)
        
        # Polite customer notification in Amharic
        reject_msg = (
            "ሰላም! የላኩልን የክፍያ ደረሰኝ ማረጋገጥ አልተቻለም። "
            "እባክዎ ትክክለኛውን የባንክ ማስተላለፊያ ስክሪንሾት እንደገና ይላኩልን ወይም በ @gibdaw ያግኙን።"
        )
        try:
            await bot.send_message(order["athlete_id"], reject_msg)
        except Exception:
            pass

    await callback.message.edit_caption(
        caption=f"{callback.message.caption or ''}\n\n❌ **RECEIPT REJECTED**",
        reply_markup=None
    )
    await callback.answer("Receipt rejected.")

# ---------------------------------------------------------
# Payouts & Revenue Split Command: /payouts
# ---------------------------------------------------------
@router.message(Command("payouts"))
async def handle_payouts_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    summary = await get_creator_payout_summary()
    report = (
        "📊 **BIRUKTAWIT FIKRE (@GIBDAW) // REVENUE & SPLIT LEDGER**\n\n"
        f"• Total Verified Sales: `{summary['total_sales']}`\n"
        f"• Total Gross Revenue: `{summary['total_gross_etb']:,.2f} ETB`\n"
        f"• Biruktawit Total Earnings: `{summary['total_creator_earnings_etb']:,.2f} ETB`\n"
        f"• Platform Total Earnings: `{summary['total_platform_earnings_etb']:,.2f} ETB`\n"
        f"• Unsettled Creator Balance: `{summary['unsettled_creator_balance_etb']:,.2f} ETB`\n\n"
        f"📈 **Tier Breakdown:**\n"
        f"  - Tier 1 (60%): `{summary['tier_1_sales_count']} sales`\n"
        f"  - Tier 2 (70%): `{summary['tier_2_sales_count']} sales`\n"
        f"🎯 **Active Tier:** `{summary['current_tier']}`\n"
    )
    if summary["sales_to_next_tier"] > 0:
        report += f"⚡ Sales remaining until permanent 70% split: `{summary['sales_to_next_tier']}`"
    else:
        report += "🚀 **PERMANENT 70% CREATOR TIER ACTIVE**"

    await message.answer(report, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

# ---------------------------------------------------------
# Funnel Analytics Command: /funnel
# ---------------------------------------------------------
@router.message(Command("funnel"))
async def handle_funnel_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = await render_funnel_report()
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

# ---------------------------------------------------------
# User Inspection Commands: /users and /user <id>
# ---------------------------------------------------------
@router.message(Command("users"))
async def handle_users_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = await render_users_report()
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

@router.message(Command("user"))
async def handle_user_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/user <telegram_id_or_username>`", parse_mode="Markdown")
        return

    query = parts[1]
    athlete = await db.get_athlete_by_id_or_username(query)
    if not athlete:
        await message.answer(f"❌ Athlete `{query}` not found in database.", parse_mode="Markdown")
        return

    t_id = athlete["telegram_id"]
    checkins = await db.get_athlete_checkins(t_id)
    orders = await db.get_athlete_order_history(t_id)

    info = (
        f"👤 **ATHLETE DOSSIER // {athlete['full_name']}**\n\n"
        f"• Telegram ID: `{t_id}`\n"
        f"• Username: @{athlete.get('username') or 'N/A'}\n"
        f"• Gender: `{athlete.get('gender') or 'N/A'}`\n"
        f"• Age: `{athlete.get('age') or 'N/A'}` | Weight: `{athlete.get('weight_kg') or 'N/A'} kg`\n"
        f"• Goal: `{athlete.get('primary_goal') or 'N/A'}`\n"
        f"• Split: `{athlete.get('days_per_week') or 'N/A'} days/week`\n"
        f"• Level: `{athlete.get('experience_level') or 'N/A'}`\n"
        f"• 📍 **Current Bot Progress:** `{athlete.get('onboarding_state')}`\n"
        f"• Last Active: `{athlete.get('last_interaction')}`\n\n"
        f"📦 **Orders ({len(orders)}):**\n"
    )
    for o in orders[:3]:
        info += f"  - `{o['order_id']}`: {o['sku']} — {o['amount_etb']} ETB [{o['status']}]\n"

    info += f"\n📝 **Weekly Check-ins Logged:** `{len(checkins)} check-ins`\n"
    for c in checkins[-4:]:
        info += f"  - Week {c['week_number']}: `{c['weight_kg']} kg` ({c['workouts_completed']} workouts)\n"

    await message.answer(info, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

async def render_users_report() -> str:
    athletes = await db.get_recent_athletes(limit=15)
    if not athletes:
        return "👥 **NO RECENT ATHLETES FOUND**"

    lines = ["👥 **RECENT ATHLETES & CURRENT BOT PROGRESS**\n"]
    for i, a in enumerate(athletes, 1):
        uname = f"@{a['username']}" if a.get("username") else "No username"
        state = a.get("onboarding_state", "START")
        gender = "👩" if a.get("gender") == "FEMALE" else ("👨" if a.get("gender") == "MALE" else "❓")
        order_st = a.get("latest_order_status")
        status_badge = f" [Order: {order_st}]" if order_st else ""

        lines.append(f"{i}. {gender} **{a['full_name']}** ({uname})")
        lines.append(f"   🆔 `{a['telegram_id']}` | 📍 State: `{state}`{status_badge}")
        lines.append(f"   🎯 Goal: `{a.get('primary_goal') or 'Not set'}` | ⚖️ `{a.get('weight_kg') or 'N/A'} kg`\n")

    lines.append("💡 *Tip:* Send `/user <id>` to inspect an athlete's complete journey and check-ins.")
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
        "📈 **CONVERSION FUNNEL & ATHLETE ANALYTICS**\n\n"
        f"👥 **Total Registered Athletes:** `{total}`\n\n"
        "🚶‍♂️ **Step-by-Step Funnel Progression:**\n"
        f"• Started Funnel: `{sc.get('START', 0)}`\n"
        f"• Gender & Age Set: `{sc.get('GENDER_SET', 0) + sc.get('AGE_SET', 0)}`\n"
        f"• Weight Profiled: `{sc.get('WEIGHT_SET', 0)}`\n"
        f"• Goal Selected: `{sc.get('GOAL_SET', 0)}`\n"
        f"• Schedule Chosen: `{sc.get('SPLIT_SET', 0)}`\n"
        f"• Diagnostic Card Generated: `{sc.get('DIAGNOSTIC_READY', 0)}`\n"
        f"• Checkout Pitch Viewed: `{sc.get('CHECKOUT_PITCHED', 0)}`\n"
        f"• Receipts Uploaded: `{sc.get('RECEIPT_SUBMITTED', 0)}`\n"
        f"• Active Paid Members: `{sc.get('ACTIVE_MEMBER', 0) + delivered}`\n\n"
        "💰 **Performance Summary:**\n"
        f"• Conversion Rate (Visit ➔ Paid): `{conv_rate:.1f}%`\n"
        f"• Total Paid Revenue: `{rev:,.2f} ETB`\n"
        f"• Pending Review Queue: `{pending} orders`"
    )

# ---------------------------------------------------------
# Settle Outstanding Balance Command: /settle
# ---------------------------------------------------------
@router.message(Command("settle"))
async def handle_settle_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    result = await settle_unsettled_payouts()
    if result["settled_count"] == 0:
        await message.answer("ℹ️ No unsettled payouts to settle at this time.")
        return

    text = (
        "✅ **CREATOR PAYOUT SETTLEMENT COMPLETED**\n\n"
        f"• Settled Records: `{result['settled_count']}`\n"
        f"• Total Transferred to Biruktawit: `{result['total_settled_etb']:,.2f} ETB`\n"
        f"• Batch Payouts: `{', '.join(result['payout_ids'][:5])}{'...' if len(result['payout_ids']) > 5 else ''}`\n\n"
        "All corresponding records in `payout_ledger` are now marked as `SETTLED`."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())

# ---------------------------------------------------------
# Inline Navigation Callbacks (English)
# ---------------------------------------------------------
@router.callback_query(F.data == "adm_view_payouts")
async def callback_view_payouts(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    summary = await get_creator_payout_summary()
    report = (
        "📊 **BIRUKTAWIT FIKRE (@GIBDAW) // REVENUE & SPLIT LEDGER**\n\n"
        f"• Total Verified Sales: `{summary['total_sales']}`\n"
        f"• Total Gross Revenue: `{summary['total_gross_etb']:,.2f} ETB`\n"
        f"• Biruktawit Total Earnings: `{summary['total_creator_earnings_etb']:,.2f} ETB`\n"
        f"• Platform Total Earnings: `{summary['total_platform_earnings_etb']:,.2f} ETB`\n"
        f"• Unsettled Creator Balance: `{summary['unsettled_creator_balance_etb']:,.2f} ETB`\n\n"
        f"📈 **Tier Breakdown:**\n"
        f"  - Tier 1 (60%): `{summary['tier_1_sales_count']} sales`\n"
        f"  - Tier 2 (70%): `{summary['tier_2_sales_count']} sales`\n"
        f"🎯 **Active Tier:** `{summary['current_tier']}`\n"
    )
    if summary["sales_to_next_tier"] > 0:
        report += f"⚡ Sales remaining until permanent 70% split: `{summary['sales_to_next_tier']}`"
    else:
        report += "🚀 **PERMANENT 70% CREATOR TIER ACTIVE**"

    await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    await callback.answer()

@router.callback_query(F.data == "adm_view_funnel")
async def callback_view_funnel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    report = await render_funnel_report()
    await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    await callback.answer()

@router.callback_query(F.data == "adm_view_users")
async def callback_view_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    report = await render_users_report()
    await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    await callback.answer()

@router.callback_query(F.data == "adm_settle_balance")
async def callback_settle_balance(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    result = await settle_unsettled_payouts()
    if result["settled_count"] == 0:
        await callback.answer("No unsettled payouts found.", show_alert=True)
        return

    text = (
        "✅ **CREATOR PAYOUT SETTLEMENT COMPLETED**\n\n"
        f"• Settled Records: `{result['settled_count']}`\n"
        f"• Total Transferred: `{result['total_settled_etb']:,.2f} ETB`\n\n"
        "Ledger status updated to `SETTLED`."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    await callback.answer("Settlement recorded successfully!")

@router.callback_query(F.data == "adm_view_catalog")
async def callback_view_catalog(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT sku, title, price_etb, pdf_path FROM workout_catalog ORDER BY sku;")

    text = "📦 **WORKOUT CATALOG SKUs & PDF BINDINGS**\n\n"
    for r in rows:
        text += f"• `{r['sku']}`: {r['title']} — **{r['price_etb']} ETB**\n  📄 `{r['pdf_path']}`\n\n"

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_catalog_keyboard())
    await callback.answer()

@router.callback_query(F.data == "adm_home")
async def callback_admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    text = (
        "🛡️ **ADMIN CONTROL DASHBOARD // BIRUKTAWIT BOT**\n\n"
        "Welcome to the admin console. Manage payments, inspect payouts, "
        "and track the 60/40 ➔ 70/30 sales ledger below."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    await callback.answer()

@router.callback_query(F.data == "adm_refresh_stats")
async def callback_refresh_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    summary = await get_creator_payout_summary()
    report = (
        "📊 **BIRUKTAWIT FIKRE (@GIBDAW) // REVENUE & SPLIT LEDGER**\n\n"
        f"• Total Verified Sales: `{summary['total_sales']}`\n"
        f"• Total Gross Revenue: `{summary['total_gross_etb']:,.2f} ETB`\n"
        f"• Biruktawit Total Earnings: `{summary['total_creator_earnings_etb']:,.2f} ETB`\n"
        f"• Platform Total Earnings: `{summary['total_platform_earnings_etb']:,.2f} ETB`\n"
        f"• Unsettled Creator Balance: `{summary['unsettled_creator_balance_etb']:,.2f} ETB`\n\n"
        f"📈 **Tier Breakdown:**\n"
        f"  - Tier 1 (60%): `{summary['tier_1_sales_count']} sales`\n"
        f"  - Tier 2 (70%): `{summary['tier_2_sales_count']} sales`\n"
        f"🎯 **Active Tier:** `{summary['current_tier']}`\n"
    )
    if summary["sales_to_next_tier"] > 0:
        report += f"⚡ Sales remaining until permanent 70% split: `{summary['sales_to_next_tier']}`"
    else:
        report += "🚀 **PERMANENT 70% CREATOR TIER ACTIVE**"

    try:
        await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_admin_home_keyboard())
    except Exception:
        pass
    await callback.answer("Metrics refreshed!")

