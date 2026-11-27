import html
import os
import logging
from aiogram import Bot
from aiogram.types import FSInputFile
from config import settings, BASE_DIR
from database.db import db
from utils.tg_helpers import format_plan_name

logger = logging.getLogger(__name__)

# Fallback filename candidates per SKU (canonical English + Amharic PDF filenames)
_SKU_PDF_CANDIDATES = {
    "BF-F-FL-3X": [
        "BF_8W_F_FatLoss_3x.pdf",
        "የ 8 ሳምንት የሴቶች ስብ ማቅለጫ እቅድ (3 ቀን በሳምንት).pdf",
    ],
    "BF-F-FL-4X": [
        "BF_8W_F_FatLoss_4x.pdf",
        "የ 8 ሳምንት የሴቶች ስብ ማቅለጫ እቅድ (4 ቀን በሳምንት).pdf",
    ],
    "BF-F-BC-3X": [
        "BF_8W_F_Booty_3x.pdf",
        "የ 8 ሳምንት የሴቶች ጡንቻ ማሳደጊያ እቅድ (3 ቀን በሳምንት).pdf",
        "የ 8 ሳምንት የሴቶች ዳሌና ቅርጽ እቅድ (3 ቀን በሳምንት).pdf",
    ],
    "BF-F-BC-4X": [
        "BF_8W_F_Booty_4x.pdf",
        "የ 8 ሳምንት የሴቶች ጡንቻ ማሳደጊያ እቅድ (4 ቀን በሳምንት).pdf",
        "የ 8 ሳምንት የሴቶች ዳሌና ቅርጽ እቅድ (4 ቀን በሳምንት).pdf",
    ],
    "BF-M-MG-3X": [
        "BF_8W_M_Hypertrophy_3x.pdf",
        "የ 8 ሳምንት የወንዶች ጡንቻ ማሳደጊያ እቅድ (3 ቀን በሳምንት).pdf",
        "የ8 ሳምንት የጀማሪዎች ጡንቻ ማሳደጊያ እቅድ (3 ቀን).pdf",
    ],
    "BF-M-MG-4X": [
        "BF_8W_M_Hypertrophy_4x.pdf",
        "የ 8 ሳምንት የወንዶች ጡንቻ ማሳደጊያ እቅድ (4 ቀን በሳምንት).pdf",
        "የ8 ሳምንት የጀማሪዎች ጡንቻ ማሳደጊያ እቅድ (4 ቀን).pdf",
    ],
    "BF-M-FL-3X": [
        "BF_8W_M_FatLoss_3x.pdf",
        "የ 8 ሳምንት የወንዶች ስብ ማቅለጫ እቅድ (3 ቀን በሳምንት).pdf",
    ],
    "BF-M-FL-4X": [
        "BF_8W_M_FatLoss_4x.pdf",
        "የ 8 ሳምንት የወንዶች ስብ ማቅለጫ እቅድ (4 ቀን በሳምንት).pdf",
    ],
}


def resolve_sku_pdf_path(sku: str, db_pdf_path: str = "") -> str:
    """Resolve existing PDF file path from DB path or known Amharic/English candidates."""
    if db_pdf_path:
        candidate = db_pdf_path if os.path.isabs(db_pdf_path) else os.path.join(BASE_DIR, db_pdf_path)
        if os.path.exists(candidate):
            return candidate
    for fname in _SKU_PDF_CANDIDATES.get(sku, []):
        p = os.path.join(settings.resolved_pdf_dir, fname)
        if os.path.exists(p):
            return p
    return ""


async def deliver_workout_program(bot: Bot, athlete_id: int, order_id: str) -> bool:
    """
    Sends the 8-week workout program PDF directly to the member.
    Uses HTML formatting and strictly personalized Birukti copy.
    """
    try:
        order = await db.get_order(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return False

        sku = order["sku"]
        athlete = await db.get_athlete(athlete_id)
        is_female = athlete and athlete.get("gender") == "FEMALE"

        async with db.pool.acquire() as conn:
            product = await conn.fetchrow("SELECT * FROM workout_catalog WHERE sku = $1;", sku)

        db_pdf_path = product["pdf_path"] if product else ""
        pdf_file = resolve_sku_pdf_path(sku, db_pdf_path)

        prog_title = html.escape(format_plan_name(sku))
        handle = html.escape(settings.CREATOR_HANDLE)

        if not pdf_file:
            if is_female:
                fallback_text = (
                    "🎉 <b>እንኳን ደስ አለሽ ቆንጆዬ! ክፍያሽ ተረጋግጧል።</b>\n\n"
                    f"የመረጥሽው ፕላን: <b>{prog_title}</b>\n\n"
                    "የ 8-ሳምንት ሙሉ PDF ፕላንሽ አሁን እየተዘጋጀልሽ ነው፣ በቅርቡ ይደርስሻል ⏳"
                )
            else:
                fallback_text = (
                    "🎉 <b>እንኳን ደስ አለህ ወንድሜ! ክፍያህ ተረጋግጧል።</b>\n\n"
                    f"የመረጥከው ፕላን: <b>{prog_title}</b>\n\n"
                    "የ 8-ሳምንት ሙሉ PDF ፕላንህ አሁን እየተዘጋጀልህ ነው፣ በቅርቡ ይደርስሃል ⏳"
                )
            await bot.send_message(athlete_id, fallback_text, parse_mode="HTML")
            return True

        document = FSInputFile(pdf_file)
        if is_female:
            caption = (
                "🎉 <b>እንኳን ደስ አለሽ ቆንጆዬ! ክፍያሽ ተረጋግጧል።</b>\n\n"
                f"ባለ 20 ገጹ የ 8-ሳምንት ፕላንሽ፣ <b>{prog_title}</b> ይሄው ደርሶሻል ✨\n\n"
                "📌 ስልክሽ ላይ Save አድርገሽ ከመጀመሪያው ገጽ ጀምረሽ በደንብ ተመልከቺው። "
                "ነገ ጂም ስትገቢ ምን እንደምትሰሪ ግራ መጋባት የለም!\n\n"
                f"ጥያቄ ካለሽ በ {handle} አናግሪኝ። መልካም ስልጠና 💪✨"
            )
        else:
            caption = (
                "🎉 <b>እንኳን ደስ አለህ ወንድሜ! ክፍያህ ተረጋግጧል።</b>\n\n"
                f"ባለ 20 ገጹ የ 8-ሳምንት ፕላንህ፣ <b>{prog_title}</b> ይሄው ደርሶሃል 🔥\n\n"
                "📌 ስልክህ ላይ Save አድርገህ ከመጀመሪያው ገጽ ጀምረህ በደንብ ተመልከተው። "
                "ነገ ጂም ስትገባ ምን እንደምትሰራ ግራ መጋባት የለም!\n\n"
                f"ጥያቄ ካለህ በ {handle} አናግረኝ። መልካም ስልጠና 💪🔥"
            )
        await bot.send_document(athlete_id, document=document, caption=caption, parse_mode="HTML")

        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET status = 'DELIVERED', delivered_at = CURRENT_TIMESTAMP WHERE order_id = $1;",
                order_id,
            )
        return True

    except Exception as e:
        logger.error(f"Failed to deliver program for order {order_id}: {e}", exc_info=True)
        return False
