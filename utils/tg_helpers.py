import asyncio
import logging
from typing import Optional
from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

_PLAN_NAME_MAP = {
    "BF-F-BC-3X": "የ8 ሳምንት የሴቶች ዳሌና ቅርጽ ማውጫ እቅድ (3 ቀን)",
    "BF-F-BC-4X": "የ8 ሳምንት የሴቶች ዳሌና ቅርጽ ማውጫ እቅድ (4 ቀን)",
    "BF-F-FL-3X": "የ8 ሳምንት የሴቶች ስብ ማቅለጫ እቅድ (3 ቀን)",
    "BF-F-FL-4X": "የ8 ሳምንት የሴቶች ስብ ማቅለጫ እቅድ (4 ቀን)",
    "BF-M-MG-3X": "የ8 ሳምንት የወንዶች ጡንቻ መገንቢያ እቅድ (3 ቀን)",
    "BF-M-MG-4X": "የ8 ሳምንት የወንዶች ጡንቻ መገንቢያ እቅድ (4 ቀን)",
    "BF-M-FL-3X": "የ8 ሳምንት የወንዶች ስብ ማቅለጫ እቅድ (3 ቀን)",
    "BF-M-FL-4X": "የ8 ሳምንት የወንዶች ስብ ማቅለጫ እቅድ (4 ቀን)",
}


_AGE_RANGE_MAP = {
    "18-24": (21, "18 - 24"),
    "25-34": (29, "25 - 34"),
    "35-44": (39, "35 - 44"),
    "45+": (45, "45+"),
}


def parse_age_callback(raw_value: str) -> tuple[int, str]:
    """Return (numeric_db_age, display_label) preserving exact range strings."""
    val = (raw_value or "").strip()
    if val in _AGE_RANGE_MAP:
        return _AGE_RANGE_MAP[val]
    if val.isdigit():
        return int(val), val
    return 25, val


def format_age_display(athlete: Optional[dict]) -> str:
    """Format exact age or range from athlete record without guessing."""
    if not athlete:
        return "N/A"
    age_range = athlete.get("age_range")
    if age_range:
        return str(age_range)
    age_num = athlete.get("age")
    if age_num is not None:
        return str(age_num)
    return "N/A"


def format_plan_name(sku: str, fallback_title: Optional[str] = None) -> str:
    """Convert internal SKU codes like BF-F-BC-4X into clean Amharic product titles."""
    key = (sku or "").strip().upper()
    if key in _PLAN_NAME_MAP:
        return _PLAN_NAME_MAP[key]
    if fallback_title:
        return fallback_title
    return "የ8 ሳምንት የጂም ስልጠና እቅድ"


async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False):
    """Acknowledge a callback immediately and swallow expired/duplicate query errors."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            return
        logger.debug("Callback answer ignored: %s", e)
    except Exception:
        pass


async def safe_delete(message: Optional[Message]):
    """Delete a message safely without raising on already-deleted or uneditable messages."""
    if not message:
        return
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception:
        pass


async def safe_typing(bot: Bot, chat_id: int, action: ChatAction = ChatAction.TYPING):
    """Send typing/upload chat action safely without blocking handler response latency."""
    try:
        await bot.send_chat_action(chat_id, action)
    except Exception:
        pass


def fire_typing(bot: Bot, chat_id: int, action: ChatAction = ChatAction.TYPING):
    """Fire-and-forget typing action to avoid adding a full Telegram RTT before logic runs."""
    return asyncio.create_task(safe_typing(bot, chat_id, action))


async def _safe_send_coro(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.warning("Background send_message failed for %s: %s", chat_id, e)


def fire_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """Fire-and-forget async send_message wrapped in a true coroutine."""
    return asyncio.create_task(_safe_send_coro(bot, chat_id, text, **kwargs))
