import asyncio
import html
import logging
from aiogram import Bot
from config import settings
from database.db import db
from keyboards.user_kb import get_payment_action_keyboard

logger = logging.getLogger("RECOVERY")


async def run_abandoned_checkout_recovery(bot: Bot) -> int:
    """
    Finds pending orders created between 25 mins and 12 hours ago with no receipt uploaded,
    and sends a grounded follow-up from Birukti with one-tap bank copy buttons.
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
    handle = html.escape(settings.CREATOR_HANDLE)
    recovery_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.BOA_ACCOUNT)

    for row in rows:
        athlete_id = row["athlete_id"]
        is_fem = row["gender"] == "FEMALE"

        if is_fem:
            text = (
                "ሰላም ቆንጆዬ 👋\n\n"
                "የ 8-ሳምንቱን ፕላንሽን ጀምረሽ ክፍያ ላይ ቆመሻል፣ የተቸገርሽበት ነገር አለ ወይስ ጥያቄ አለሽ?\n\n"
                "ከታች ባሉት CBE ወይም BOA ቁጥሮች ከፍለሽ ደረሰኙን እዚህ ብትልኪ ወዲያው ፕላንሽ ይላክልሻል። "
                f"ጥያቄ ካለሽ በ {handle} ጻፊልኝ።"
            )
        else:
            text = (
                "ሰላም ወንድሜ 👋\n\n"
                "የ 8-ሳምንቱን ፕላንህን ጀምረህ ክፍያ ላይ ቆመሃል፣ የተቸገርክበት ነገር አለ ወይስ ጥያቄ አለህ?\n\n"
                "ከታች ባሉት CBE ወይም BOA ቁጥሮች ከፍለህ ደረሰኙን እዚህ ብትልክ ወዲያው ፕላንህ ይላክልሃል። "
                f"ጥያቄ ካለህ በ {handle} ጻፍልኝ።"
            )

        try:
            await bot.send_message(athlete_id, text, parse_mode="HTML", reply_markup=recovery_kb)
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE orders SET recovery_sent = TRUE WHERE order_id = $1;",
                    row["order_id"]
                )
            sent_count += 1
            await asyncio.sleep(0.08)
        except Exception as e:
            logger.warning(f"Failed recovery message to member {athlete_id}: {e}")

    return sent_count


async def recovery_scheduler_loop(bot: Bot):
    """
    Background worker that checks abandoned checkouts every 15 minutes.
    """
    logger.info("Starting Abandoned Checkout Recovery background loop...")
    while True:
        try:
            await asyncio.sleep(900)
            recovered = await run_abandoned_checkout_recovery(bot)
            if recovered > 0:
                logger.info(f"Abandoned Checkout Recovery sent reminders to {recovered} members.")
        except asyncio.CancelledError:
            logger.info("Checkout recovery worker cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in checkout recovery loop: {e}", exc_info=True)
            await asyncio.sleep(60)
