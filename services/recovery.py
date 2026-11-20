import asyncio
import logging
from aiogram import Bot
from database.db import db

logger = logging.getLogger("RECOVERY")

async def run_abandoned_checkout_recovery(bot: Bot) -> int:
    """
    Finds pending orders created between 25 mins and 12 hours ago with no receipt uploaded,
    and sends a warm, personal follow-up from Birukti.
    """
    query = """
    SELECT o.order_id, o.athlete_id, o.sku, a.gender, a.full_name
    FROM orders o
    JOIN athletes a ON o.athlete_id = a.telegram_id
    WHERE o.status = 'PENDING'
      AND o.receipt_file_id IS NULL
      AND o.recovery_sent = FALSE
      AND o.created_at <= CURRENT_TIMESTAMP - INTERVAL '25 minutes'
      AND o.created_at >= CURRENT_TIMESTAMP - INTERVAL '12 hours';
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)

    sent_count = 0
    for row in rows:
        athlete_id = row["athlete_id"]
        is_fem = row["gender"] == "FEMALE"

        if is_fem:
            text = (
                "ሰላም ቆንጆዬ! 👋\n\n"
                "የ 8-ሳምንት የትራንስፎርሜሽን ፕሮግራምሽን ክፍያ ለመፈጸም የተቸገርሽበት ነገር አለ? "
                "ወይስ ጥያቄ ኖሮሽ ነው?\n\n"
                "ክፍያውን በ CBE፣ አቢሲኒያ ወይም በቴሌብር እንደፈጸምሽ ደረሰኝሽን እዚህ ላኪልኝ። "
                "ማንኛውም ጥያቄ ካለሽ በ @gibdaw በቀጥታ ማናገር ትችያለሽ! አብረን እንሰራዋለን 💪✨"
            )
        else:
            text = (
                "ሰላም ወንድሜ! 👋\n\n"
                "የ 8-ሳምንት የትራንስፎርሜሽን ፕሮግራምህን ክፍያ ለመፈጸም የተቸገርክበት ነገር አለ? "
                "ወይስ ጥያቄ ኖሮህ ነው?\n\n"
                "ክፍያውን በ CBE፣ አቢሲኒያ ወይም በቴሌብር እንደፈጸምክ ደረሰኝህን እዚህ ላክልኝ። "
                "ማንኛውም ጥያቄ ካለህ በ @gibdaw በቀጥታ አናግረኝ! አብረን እንሰራዋለን 💪🔥"
            )

        try:
            await bot.send_message(athlete_id, text)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE orders SET recovery_sent = TRUE WHERE order_id = $1;",
                    row["order_id"]
                )
            sent_count += 1
            await asyncio.sleep(0.08)  # Telegram anti-flood pacing
        except Exception as e:
            logger.warning(f"Failed recovery message to athlete {athlete_id}: {e}")

    return sent_count

async def recovery_scheduler_loop(bot: Bot, interval_seconds: int = 600):
    """
    Runs in the background every 10 minutes to recover abandoned checkouts.
    """
    logger.info("Starting Abandoned Checkout Recovery background loop...")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            recovered = await run_abandoned_checkout_recovery(bot)
            if recovered > 0:
                logger.info(f"Abandoned checkout recovery sent follow-ups to {recovered} athletes.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in recovery scheduler loop: {e}", exc_info=True)

