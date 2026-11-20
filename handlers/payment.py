import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from database.db import db
from config import settings
from services.verifier import extract_transaction_reference, is_valid_biruktawit_receiver
from keyboards.admin_kb import get_admin_review_keyboard

router = Router()
logger = logging.getLogger(__name__)

async def process_receipt_submission(
    message: Message,
    bot: Bot,
    file_id: str,
    is_document: bool = False,
    caption_text: str = ""
):
    user_id = message.from_user.id

    # 1. Fetch user's pending order
    pending_order = await db.get_latest_pending_order(user_id)
    if not pending_order:
        await message.answer(
            "ለማረጋገጥ የሚፈለግ የትዕዛዝ መረጃ አላገኘንም። እባክዎ መጀመሪያ /start ብለው የሚፈልጉትን ፕሮግራም ይምረጡ።"
        )
        return

    order_id = pending_order["order_id"]
    sku = pending_order["sku"]
    amount = pending_order["amount_etb"]

    # 2. Extract potential transaction reference from caption
    txn_ref = extract_transaction_reference(caption_text)

    # 3. Check for receipt replay fraud
    replay_warning = ""
    if txn_ref:
        existing = await db.check_txn_replay(txn_ref)
        if existing and existing.get("order_id") != order_id:
            replay_warning = f"\n⚠️ **REPLAY WARNING: Reference `{txn_ref}` was already verified in `{existing['order_id']}`!**\n"

    # 4. Update order with receipt file_id & txn_ref
    await db.update_order_receipt(order_id, file_id, txn_ref)
    await db.update_athlete_field(user_id, "onboarding_state", "RECEIPT_SUBMITTED")

    # 5. Send friendly confirmation to the athlete in Addis Amharic
    await message.answer(
        "ደረሰኝዎ ደርሶናል! እናመሰግናለን 🙏\n\n"
        "የከፈሉበትን መረጃ በ 1-3 ደቂቃ ውስጥ አረጋግጠን የ 8-ሳምንቱን ሙሉ ፕሮግራም በ PDF እንልክልዎታለን። "
        "እባክዎ ትንሽ ይጠብቁ... ⏳"
    )

    # 6. Format Admin Review Alert in English
    admin_caption = (
        f"🔔 **NEW PAYMENT SLIP SUBMITTED // {order_id}**\n\n"
        f"👤 **Athlete:** {message.from_user.full_name} (@{message.from_user.username or 'N/A'})\n"
        f"🆔 **Telegram ID:** `{user_id}`\n"
        f"📦 **Program SKU:** `{sku}`\n"
        f"💰 **Amount:** `{amount} ETB`\n"
        f"🔖 **Extracted Ref:** `{txn_ref or 'Pending OCR'}`\n"
        f"{replay_warning}\n"
        f"Review receipt and take action below 👇"
    )

    review_kb = get_admin_review_keyboard(order_id)

    # Dispatch to Admin Channel or individual Admins
    target_chats = []
    if settings.ADMIN_CHANNEL_ID:
        target_chats.append(settings.ADMIN_CHANNEL_ID)
    else:
        target_chats.extend(settings.admin_ids_list)

    for chat_id in target_chats:
        try:
            if is_document:
                await bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=admin_caption,
                    parse_mode="Markdown",
                    reply_markup=review_kb
                )
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=admin_caption,
                    parse_mode="Markdown",
                    reply_markup=review_kb
                )
        except Exception as e:
            logger.error(f"Failed to alert admin {chat_id}: {e}")

# Photo Upload Handler
@router.message(F.photo)
async def handle_receipt_photo(message: Message, bot: Bot):
    photo = message.photo[-1]
    await process_receipt_submission(
        message=message,
        bot=bot,
        file_id=photo.file_id,
        is_document=False,
        caption_text=message.caption or ""
    )

# Document / PDF Receipt Handler
@router.message(F.document)
async def handle_receipt_document(message: Message, bot: Bot):
    doc = message.document
    await process_receipt_submission(
        message=message,
        bot=bot,
        file_id=doc.file_id,
        is_document=True,
        caption_text=message.caption or ""
    )
