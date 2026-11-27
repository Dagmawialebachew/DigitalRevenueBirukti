import html
import logging
import traceback
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent, BufferedInputFile
from config import settings
from database.db import db

logger = logging.getLogger("ERROR_GUARD")

# Harmless Telegram API race/staleness messages to absorb silently (zero terminal noise)
BENIGN_TELEGRAM_ERRORS = (
    "query is too old",
    "query id is invalid",
    "message is not modified",
    "message to delete not found",
    "message can't be deleted",
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
)


def is_benign_telegram_error(exc: BaseException) -> bool:
    if isinstance(exc, TelegramForbiddenError):
        return True
    msg = str(exc).lower()
    return any(pattern in msg for pattern in BENIGN_TELEGRAM_ERRORS)


async def global_error_handler(event: ErrorEvent):
    """
    Global dispatcher error boundary modeled after CoachHilawe's error forwarding pattern:
    - Silently absorbs benign Telegram noise (stale callback queries, deleted messages, blocked users).
    - Logs unexpected exceptions cleanly and dispatches a traceback .txt document + summary card
      to the configured error group (ADMIN_ERROR_GID -> fallback to ADMIN_PAYMENT_GID -> admin IDs).
    """
    exc = event.exception

    if is_benign_telegram_error(exc):
        logger.debug("Ignored benign Telegram error: %s", exc)
        return True

    logger.error("Unhandled engine exception on update: %s", exc, exc_info=exc)

    update = event.update
    bot = update.bot
    user = None
    if update.message:
        user = update.message.from_user
    elif update.callback_query:
        user = update.callback_query.from_user

    user_id = user.id if user else 0
    username = f"@{html.escape(user.username)}" if user and user.username else "No Username"
    full_name = html.escape(user.full_name) if user and user.full_name else "Unknown"

    # Resolve error notification targets (Error group -> Payment group -> Admin IDs)
    target_chats = []
    if settings.ADMIN_ERROR_GID:
        target_chats.append(settings.ADMIN_ERROR_GID)
    elif settings.ADMIN_PAYMENT_GID:
        target_chats.append(settings.ADMIN_PAYMENT_GID)
    elif settings.ADMIN_CHANNEL_ID:
        target_chats.append(settings.ADMIN_CHANNEL_ID)
    elif settings.admin_ids_list:
        target_chats.extend(settings.admin_ids_list)

    if bot and target_chats:
        try:
            tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            log_file = BufferedInputFile(tb_text.encode("utf-8"), filename=f"error_{user_id}.txt")

            caption = (
                "❌ <b>ENGINE EXCEPTION</b>\n"
                "━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> {full_name} ({username})\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"⚠️ <b>Type:</b> <code>{html.escape(type(exc).__name__)}</code>\n"
                f"📝 <b>Error:</b> <code>{html.escape(str(exc)[:180])}</code>"
            )

            for chat_id in target_chats:
                try:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=log_file,
                        caption=caption,
                        parse_mode="HTML",
                    )
                except Exception as send_err:
                    logger.warning(f"Failed sending error log to {chat_id}: {send_err}")
        except Exception as prep_err:
            logger.warning(f"Failed building error alert payload: {prep_err}")

    # Notify user cleanly (gender-personalized if profile already has gender)
    try:
        support_ref = f"@{html.escape(settings.SUPPORT_BOT_USERNAME)}"
        athlete = await db.get_athlete(user_id) if user_id else None
        gender = (athlete or {}).get("gender")

        if gender == "FEMALE":
            user_msg = (
                "⚠️ ትንሽ ቴክኒካል ችግር ተፈጥሯል፣ ቡድናችንን አሳውቀናል።\n"
                f"ትንሽ ቆይተሽ እንደገና ሞክሪ ወይም {support_ref} ላይ ጻፊልን።"
            )
            alert_msg = "⚠️ ችግር ተፈጥሯል፣ ትንሽ ቆይተሽ እንደገና ሞክሪ።"
        elif gender == "MALE":
            user_msg = (
                "⚠️ ትንሽ ቴክኒካል ችግር ተፈጥሯል፣ ቡድናችንን አሳውቀናል።\n"
                f"ትንሽ ቆይተህ እንደገና ሞክር ወይም {support_ref} ላይ ጻፍልን።"
            )
            alert_msg = "⚠️ ችግር ተፈጥሯል፣ ትንሽ ቆይተህ እንደገና ሞክር።"
        else:
            user_msg = (
                "⚠️ ትንሽ ቴክኒካል ችግር ተፈጥሯል፣ ቡድናችንን አሳውቀናል።\n"
                f"እባክዎ ትንሽ ቆይተው እንደገና ይሞክሩ ወይም {support_ref} ላይ ይጻፉ።"
            )
            alert_msg = "⚠️ ችግር ተፈጥሯል፣ እባክዎ እንደገና ይሞክሩ።"

        if update.message:
            await update.message.answer(user_msg, parse_mode="HTML")
        elif update.callback_query:
            try:
                await update.callback_query.answer(alert_msg, show_alert=True)
            except TelegramBadRequest:
                pass
    except Exception:
        pass

    return True
