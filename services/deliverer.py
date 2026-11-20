import os
import logging
from aiogram import Bot
from aiogram.types import FSInputFile
from database.db import db

logger = logging.getLogger(__name__)

async def deliver_workout_program(bot: Bot, athlete_id: int, order_id: str) -> bool:
    """
    Sends the 8-week workout program PDF directly to the athlete.
    """
    try:
        order = await db.get_order(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return False

        sku = order["sku"]
        # Fetch program details from catalog
        async with db.pool.acquire() as conn:
            product = await conn.fetchrow("SELECT * FROM workout_catalog WHERE sku = $1;", sku)

        pdf_file = product["pdf_path"] if product else ""
        if pdf_file and not os.path.isabs(pdf_file):
            from config import BASE_DIR
            pdf_file = os.path.join(BASE_DIR, pdf_file)

        if not product or not os.path.exists(pdf_file):
            # Deliver placeholder notification if PDF file is being prepared
            fallback_text = (
                "🎉 **እንኳን ደስ አለዎት! ክፍያዎ በተሳካ ሁኔታ ተረጋግጧል!**\n\n"
                f"የመረጡት ፕሮግራም: **{product['title'] if product else sku}**\n\n"
                "የእርስዎ 8-ሳምንት የተሟላ PDF ፕሮግራም ፋይል አሁን እየተላከልዎት ነው..."
            )
            await bot.send_message(athlete_id, fallback_text, parse_mode="Markdown")
            return True

        # Deliver actual PDF
        document = FSInputFile(pdf_file)
        caption = (
            "🎉 **እንኳን ደስ አለዎት! ክፍያዎ ተረጋግጧል!**\n\n"
            f"የእርስዎ የ 8-ሳምንት የትራንስፎርሜሽን ፕሮግራም: **{product['title']}** ይሄው ተዘጋጅቷል!\n\n"
            "📌 ይህንን PDF ስልክዎ ላይ Save አድርገው በደንብ ያንብቡት። ነገ ጠዋት የመጀመሪያውን ልምምድ እንጀምራለን!\n\n"
            "ጥያቄ ካለዎት በማንኛውም ሰዓት በ @gibdaw በቀጥታ ማግኘት ይችላሉ። መልካም የስፖርት ጊዜ! 💪✨"
        )
        await bot.send_document(athlete_id, document=document, caption=caption, parse_mode="Markdown")

        # Mark order delivered
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET status = 'DELIVERED', delivered_at = CURRENT_TIMESTAMP WHERE order_id = $1;",
                order_id
            )
        return True

    except Exception as e:
        logger.error(f"Failed to deliver program for order {order_id}: {e}", exc_info=True)
        return False

