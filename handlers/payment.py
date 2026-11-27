import html
import logging
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message
from database.db import db
from config import settings
from services.verifier import extract_transaction_reference
from keyboards.admin_kb import get_admin_review_keyboard
from utils.tg_helpers import format_plan_name

router = Router()
logger = logging.getLogger(__name__)


def _payment_target_chats() -> list[int]:
    payment_channel = settings.ADMIN_PAYMENT_GID or settings.ADMIN_CHANNEL_ID
    if payment_channel:
        return [payment_channel]
    return list(settings.admin_ids_list)


def _auto_resolve_sku(athlete: dict | None) -> str:
    if not athlete:
        return "BF-F-BC-4X"
    is_fem = athlete.get("gender") == "FEMALE"
    raw_goal = athlete.get("primary_goal") or ("BOOTY_CURVES" if is_fem else "MUSCLE_GAIN")
    days = 3 if athlete.get("days_per_week") == 3 else 4
    if is_fem:
        return f"BF-F-FL-{days}X" if raw_goal == "FAT_LOSS" else f"BF-F-BC-{days}X"
    return f"BF-M-FL-{days}X" if raw_goal == "FAT_LOSS" else f"BF-M-MG-{days}X"


async def process_receipt_submission(
    message: Message,
    bot: Bot,
    file_id: str,
    is_document: bool = False,
    caption_text: str = "",
):
    """Automatically forward ANY user image or payment document to the payment group."""
    user_id = message.from_user.id
    full_name = message.from_user.full_name or "አባል"
    username = message.from_user.username

    athlete = await db.get_athlete(user_id)
    if not athlete:
        athlete = await db.upsert_athlete(user_id, full_name, username)

    is_female = athlete.get("gender") == "FEMALE"
    has_gender = athlete.get("gender") in ("FEMALE", "MALE")
    txn_ref = extract_transaction_reference(caption_text)

    pending_order = await db.get_latest_pending_order(user_id)
    is_update = False

    # Auto-create a pending order if the user uploaded a slip directly before reaching checkout
    if not pending_order:
        async with db.pool.acquire() as conn:
            active_order = await conn.fetchrow(
                "SELECT sku FROM orders WHERE athlete_id = $1 AND status IN ('VERIFIED', 'DELIVERED') ORDER BY created_at DESC LIMIT 1;",
                user_id,
            )

        if active_order:
            # Paid member sent an image -> forward straight to payment group for visibility anyway
            safe_name = html.escape(full_name)
            safe_uname = f"@{html.escape(username)}" if username else "N/A"
            plan_label = html.escape(format_plan_name(active_order["sku"]))
            fwd_caption = (
                "🖼️ <b>IMAGE FROM ACTIVE MEMBER</b>\n\n"
                f"👤 <b>Member:</b> {safe_name} ({safe_uname})\n"
                f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
                f"📦 <b>Active Plan:</b> {plan_label}\n"
            )
            if caption_text:
                fwd_caption += f"📝 <b>Caption:</b> <i>{html.escape(caption_text[:300])}</i>\n"

            for chat_id in _payment_target_chats():
                try:
                    if is_document:
                        await bot.send_document(chat_id=chat_id, document=file_id, caption=fwd_caption, parse_mode="HTML")
                    else:
                        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=fwd_caption, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed forwarding active member image to {chat_id}: {e}")

            ack = (
                "ፎቶሽን ተቀብለናል ቆንጆዬ! ✅"
                if is_female else
                "ፎቶህን ተቀብለናል ወንድሜ! ✅"
            )
            await message.answer(ack, parse_mode="HTML")
            return

        sku = _auto_resolve_sku(athlete)
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        pending_order = await db.create_order(order_id, user_id, sku, settings.DEFAULT_PRICE_ETB)
    else:
        order_id = pending_order["order_id"]
        sku = pending_order["sku"]
        is_update = bool(pending_order.get("receipt_file_id"))

    amount = pending_order["amount_etb"]

    replay_warning = ""
    if txn_ref:
        existing = await db.check_txn_replay(txn_ref)
        if existing and existing.get("order_id") != order_id:
            replay_warning = (
                f"\n⚠️ <b>REPLAY WARNING:</b> Reference <code>{html.escape(txn_ref)}</code> "
                f"was already verified in <code>{html.escape(existing['order_id'])}</code>!\n"
            )

    await db.update_order_receipt(order_id, file_id, txn_ref)
    await db.update_athlete_field(user_id, "onboarding_state", "RECEIPT_SUBMITTED")

    if has_gender and is_female:
        confirm_text = (
            "ደረሰኝሽ ደርሶኛል ቆንጆዬ! 🙏\n\n"
            "በ 1 እስከ 3 ደቂቃ ውስጥ አረጋግጬ ባለ 20 ገጹን የ 8-ሳምንት ፕላንሽን PDF እልክልሻለሁ፣ ትንሽ ጠብቂ... ⏳"
        )
    elif has_gender:
        confirm_text = (
            "ደረሰኝህ ደርሶኛል ወንድሜ! 🙏\n\n"
            "በ 1 እስከ 3 ደቂቃ ውስጥ አረጋግጬ ባለ 20 ገጹን የ 8-ሳምንት ፕላንህን PDF እልክልሃለሁ፣ ትንሽ ጠብቅ... ⏳"
        )
    else:
        confirm_text = (
            "ደረሰኙ ደርሶናል! 🙏\n\n"
            "በ 1 እስከ 3 ደቂቃ ውስጥ አረጋግጠን ባለ 20 ገጹን ፕላን በ PDF እንልካለን፣ ትንሽ ይጠብቁ... ⏳"
        )
    await message.answer(confirm_text, parse_mode="HTML")

    safe_name = html.escape(full_name)
    safe_uname = f"@{html.escape(username)}" if username else "N/A"
    header_tag = "UPDATED PAYMENT SLIP" if is_update else "NEW PAYMENT SLIP SUBMITTED"
    safe_plan = html.escape(format_plan_name(sku))

    admin_caption = (
        f"🔔 <b>{header_tag} // {html.escape(order_id)}</b>\n\n"
        f"👤 <b>Member:</b> {safe_name} ({safe_uname})\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"📦 <b>Program:</b> {safe_plan}\n"
        f"💰 <b>Amount:</b> <code>{amount} ETB</code>\n"
        f"🔖 <b>Extracted Ref:</b> <code>{html.escape(txn_ref) if txn_ref else 'Pending OCR'}</code>\n"
        f"{replay_warning}\n"
        "Review receipt and take action below 👇"
    )

    review_kb = get_admin_review_keyboard(order_id)
    for chat_id in _payment_target_chats():
        try:
            if is_document:
                await bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=review_kb,
                )
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=review_kb,
                )
        except Exception as e:
            logger.error(f"Failed to alert payment group {chat_id}: {e}")


@router.message(F.photo)
async def handle_receipt_photo(message: Message, bot: Bot):
    photo = message.photo[-1]
    await process_receipt_submission(
        message=message,
        bot=bot,
        file_id=photo.file_id,
        is_document=False,
        caption_text=message.caption or "",
    )


@router.message(F.document)
async def handle_receipt_document(message: Message, bot: Bot):
    doc = message.document
    await process_receipt_submission(
        message=message,
        bot=bot,
        file_id=doc.file_id,
        is_document=True,
        caption_text=message.caption or "",
    )
