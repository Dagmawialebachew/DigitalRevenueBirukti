import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.db import db
from handlers.onboarding import router as onboarding_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BiruktawitBot")

async def main():
    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Please configure it in .env file.")
        return

    # 1. Initialize Database connection
    logger.info("Connecting to database...")
    await db.connect()

    # 2. Initialize Bot and Dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 3. Register Routers
    dp.include_router(admin_router)
    dp.include_router(payment_router)
    dp.include_router(onboarding_router)

    # 4. Start Background Abandoned Checkout Recovery Engine
    from services.recovery import recovery_scheduler_loop
    recovery_task = asyncio.create_task(recovery_scheduler_loop(bot))

    logger.info("Bot starting in polling mode...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down bot & closing database...")
        recovery_task.cancel()
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")

