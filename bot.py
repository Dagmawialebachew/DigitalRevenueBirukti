import asyncio
import logging
import os
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import settings
from database.db import db
from handlers.onboarding import router as onboarding_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router
from middlewares.error_handler import global_error_handler
from services.recovery import recovery_scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("BiruktawitBot")


async def health_check(request: web.Request) -> web.Response:
    """Fast HTTP health check endpoint for Render / Docker."""
    db_ok = bool(db.pool is not None)
    return web.json_response({
        "status": "ok",
        "db": "connected" if db_ok else "initializing",
        "service": "BiruktawitBot",
        "creator": settings.CREATOR_HANDLE,
    })


def _resolve_webhook_base() -> str:
    """Resolve webhook base URL from explicit WEBHOOK_URL or Render's auto-injected RENDER_EXTERNAL_URL."""
    return (
        settings.WEBHOOK_URL.strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


def create_app() -> web.Application:
    """Create and configure the aiohttp web application with health checks, error boundary & bot lifecycle."""
    app = web.Application()

    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Global error boundary (catches exceptions from ALL child routers & forwards to error group)
    dp.error.register(global_error_handler)

    # Register Routers (onboarding_router last because it owns the catch-all inquiry forwarder)
    dp.include_router(admin_router)
    dp.include_router(payment_router)
    dp.include_router(onboarding_router)

    app["bot"] = bot
    app["dp"] = dp

    webhook_base = _resolve_webhook_base()
    if webhook_base:
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)

    async def on_startup(app_instance: web.Application):
        logger.info("Initializing warm PostgreSQL pool...")
        await db.connect()

        app_instance["recovery_task"] = asyncio.create_task(recovery_scheduler_loop(bot))

        if webhook_base:
            webhook_target = f"{webhook_base.rstrip('/')}/webhook"
            logger.info("Setting Telegram webhook to: %s", webhook_target)
            try:
                await bot.set_webhook(webhook_target, drop_pending_updates=True)
            except Exception as e:
                logger.warning("Failed setting webhook on startup (retrying later or already set): %s", e)
        else:
            logger.info("No webhook URL provided. Starting Telegram polling engine...")
            await bot.delete_webhook(drop_pending_updates=True)
            app_instance["polling_task"] = asyncio.create_task(dp.start_polling(bot))

    async def on_cleanup(app_instance: web.Application):
        logger.info("Shutting down bot & closing resources...")
        if "recovery_task" in app_instance:
            app_instance["recovery_task"].cancel()
        if "polling_task" in app_instance:
            try:
                await dp.stop_polling()
            except Exception:
                pass
            app_instance["polling_task"].cancel()
        await db.close()
        await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


def find_available_port(start_port: int) -> int:
    """Check if the target port is free; if not, pick next available port locally."""
    import socket
    if os.getenv("RENDER"):
        return start_port
    for p in [start_port, start_port + 1, 8085, 8088, 9000]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return start_port


def main():
    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Configure it in environment variables or .env file.")
        sys.exit(1)

    preferred_port = int(os.getenv("PORT", str(settings.PORT)))
    port = find_available_port(preferred_port)
    if port != preferred_port:
        logger.warning("Port %s is busy locally. Using available port %s instead.", preferred_port, port)

    logger.info("Starting BiruktawitBot web service on 0.0.0.0:%s", port)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
