import asyncio
import html
import logging
import os
import re
import uuid
from typing import Optional, Tuple

from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db import db
from keyboards.user_kb import (
    get_user_main_menu,
    get_support_keyboard,
    get_gender_keyboard,
    get_age_keyboard,
    get_weight_keyboard,
    get_goal_keyboard,
    get_frequency_keyboard,
    get_commitment_keyboard,
    get_offer_cta_keyboard,
    get_payment_action_keyboard,
    get_athlete_plan_keyboard,
    get_checkin_workouts_keyboard,
    get_resume_keyboard,
)
from services.diagnostics import generate_athlete_diagnostic_card
from utils.tg_helpers import (
    safe_answer,
    safe_delete,
    fire_typing,
    fire_send,
    format_plan_name,
    parse_age_callback,
    format_age_display,
)

router = Router()
logger = logging.getLogger(__name__)


class IntakeFSM(StatesGroup):
    age = State()
    weight = State()


class CheckinFSM(StatesGroup):
    weight = State()
    workouts = State()


MENU_TEXTS = {
    "🏋️‍♀️ የኔ ፕላን", "🏋️‍♀️ የእኔ ፕሮግራም",
    "💳 ክፍያ / ደረሰኝ", "💳 ክፍያ ፈጽም / ደረሰኝ ላክ",
    "🎁 ነፃ መመሪያ", "🎁 ነፃ የፎርም መመሪያ (PDF)",
    "ℹ️ ስለ ብሩክቲ", "ℹ️ ስለ ብሩክታዊት (@gebdaw)",
}

# In-memory Telegram file_id cache to avoid re-uploading bytes on every /start
_cached_welcome_file_ids: list[str] = []


def extract_age(text: str) -> int | None:
    match = re.search(r"\b(1[4-9]|[2-8][0-9]|90)\b", text)
    if match:
        return int(match.group(1))
    return None


def extract_weight(text: str) -> float | None:
    match = re.search(r"\b([3-9][0-9]|1[0-9]{2}|200)(?:\.([0-9]+))?\b", text)
    if match:
        return float(match.group(0))
    return None


def _resolve_sku_and_goal(is_female: bool, raw_goal: str, days: int) -> Tuple[str, str]:
    """Map user gender, goal, and weekly days into one of the 8 core PDF SKUs."""
    safe_days = 3 if days == 3 else 4
    if is_female:
        if raw_goal == "FAT_LOSS":
            return f"BF-F-FL-{safe_days}X", "የሴቶች ስብ ማቅለጫ"
        return f"BF-F-BC-{safe_days}X", "የሴቶች ዳሌና ቅርጽ"
    if raw_goal == "FAT_LOSS":
        return f"BF-M-FL-{safe_days}X", "የወንዶች ስብ ማቅለጫ"
    return f"BF-M-MG-{safe_days}X", "የወንዶች ጡንቻ መገንቢያ"


async def _get_or_create_pending_order(user_id: int, sku: str) -> str:
    """Reuse an existing pending order for the same SKU or create a fresh one."""
    pending = await db.get_latest_pending_order(user_id)
    if pending and pending.get("sku") == sku and not pending.get("receipt_file_id"):
        return pending["order_id"]
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    await db.create_order(order_id, user_id, sku, settings.DEFAULT_PRICE_ETB)
    return order_id


def _build_pitch_text(is_female: bool, goal_name: str) -> str:
    """Stage 1: CoachHilawe-inspired psychological conversion offer with strikethrough discount (no bank accounts here)."""
    price = settings.DEFAULT_PRICE_ETB
    anchor_price = 1500

    if is_female:
        return (
            f"🎯 <b>{html.escape(goal_name)} ፕላንሽ ዝግጁ ነው!</b>\n\n"
            "አብዛኛው ሰው ጂም ገብቶ የሚደክመው ያለ ግልጽ እቅድ ስለሚሰራ እና ምን እንደሚመገብ ስለማያውቅ ነው። "
            "ይህንን ችግር አንዴ ለመጨረሻ ጊዜ እንድትፈቺ ባለ 20 ገጹ <b>የ 8-ሳምንት ፕላንሽ</b> ተዘጋጅቷል 🏆\n\n"
            "<b>ፕላንሽ ውስጥ ምን ምን አለ?</b>\n"
            "🎥 <b>ለእያንዳንዱ እንቅስቃሴ ቪዲዮ ሊንኮች:</b> ጂም ስትገቢ ምን እንደምትሰሪ ግራ እንዳይጋባሽ\n"
            "✅ <b>Sets, Reps እና 1-2 RIR ህግ:</b> ሳትጎጂ ጡንቻሽን በትክክል የምታሰሪበት መለኪያ\n"
            "✅ <b>Warm-up, Mobility እና Cool-down:</b> ከልምምድ በፊትና በኋላ የሚሰራ ሙሉ እቅድ\n"
            "✅ <b>የኢትዮጵያ ምግቦች መመሪያ:</b> በሽሮ፣ በእንጀራ፣ በእንቁላልና በአጃ ካሎሪና ፕሮቲንሽን እንዴት እንደምታሟይ\n\n"
            "⚡️ <b>ልዩ የምዝገባ ቅናሽ</b>\n"
            f"<s>{anchor_price:,} ብር</s> ➡️ <code>{price} ብር</code>\n"
            "💎 አሁን ስለጀመርሽ <b>የ 37% ቅናሽ</b> ተግብረንልሻል።\n\n"
            "<b>አሁን ፕላንሽን ከፍተሽ ትክክለኛውን ለውጥ ትጀምሪያለሽ ወይስ እንደበፊቱ ባለሽበት ትቆያለሽ? 👇</b>"
        )

    return (
        f"🎯 <b>{html.escape(goal_name)} ፕላንህ ዝግጁ ነው!</b>\n\n"
        "አብዛኛው ሰው ጂም ገብቶ የሚደክመው ያለ ግልጽ እቅድ ስለሚሰራ እና ምን እንደሚመገብ ስለማያውቅ ነው። "
        "ይህንን ችግር አንዴ ለመጨረሻ ጊዜ እንድትፈታ ባለ 20 ገጹ <b>የ 8-ሳምንት ፕላንህ</b> ተዘጋጅቷል 🏆\n\n"
        "<b>ፕላንህ ውስጥ ምን ምን አለ?</b>\n"
        "🎥 <b>ለእያንዳንዱ እንቅስቃሴ ቪዲዮ (CLICK HERE):</b> ጂም ስትገባ ምን እንደምትሰራ ግራ እንዳይጋባህ\n"
        "✅ <b>Sets, Reps እና 1-2 RIR ህግ:</b> ሳትጎዳ ጡንቻህን በትክክል የምታሰራበት መለኪያ\n"
        "✅ <b>Warm-up, Mobility እና Cool-down:</b> ከልምምድ በፊትና በኋላ የሚሰራ ሙሉ ፕሮቶኮል\n"
        "✅ <b>የኢትዮጵያ ምግቦች መመሪያ:</b> በሽሮ፣ በእንጀራ፣ በእንቁላልና በአጃ ካሎሪና ፕሮቲንህን እንዴት እንደምታሟላ\n\n"
        "⚡️ <b>ልዩ የምዝገባ ቅናሽ</b>\n"
        f"<s>{anchor_price:,} ብር</s> ➡️ <code>{price} ብር</code>\n"
        "💎 አሁን ስለጀመርክ <b>የ 37% ቅናሽ</b> ተግብረንልሃል።\n\n"
        "<b>አሁን ፕላንህን ከፍተህ ትክክለኛውን ለውጥ ትጀምራለህ ወይስ እንደበፊቱ ባለህበት ትቆያለህ? 👇</b>"
    )


def _build_payment_page_text(is_female: bool, sku: str) -> str:
    """Stage 2: Dedicated clean bank copy page (CBE & BOA only, direct screenshot instruction)."""
    price = settings.DEFAULT_PRICE_ETB
    plan_label = html.escape(format_plan_name(sku))
    cbe_acc = html.escape(settings.CBE_ACCOUNT)
    cbe_holder = html.escape(settings.CBE_ACCOUNT_HOLDER)
    boa_acc = html.escape(settings.BOA_ACCOUNT)
    boa_holder = html.escape(settings.BOA_ACCOUNT_HOLDER)

    tail = (
        "📸 <b>ክፍያውን እንደጨረሽ የደረሰኙን Screenshot እዚህ ላኪ!</b>\n"
        "እንዳየሁት ወዲያውኑ ሙሉውን PDF እልክልሻለሁ 🚀"
        if is_female else
        "📸 <b>ክፍያውን እንደጨረስክ የደረሰኙን Screenshot እዚህ ላክ!</b>\n"
        "እንዳየሁት ወዲያውኑ ሙሉውን PDF እልክልሃለሁ 🚀"
    )

    return (
        "💳 <b>የመክፈያ ባንክ አካውንቶች</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📦 <b>ፕላን:</b> {plan_label}\n"
        f"💰 <b>ክፍያ:</b> <code>{price} ብር</code>\n\n"
        f"🏦 <b>ንግድ ባንክ (CBE):</b> <code>{cbe_acc}</code>\n"
        f"👤 <b>ስም:</b> {cbe_holder}\n\n"
        f"🏦 <b>አቢሲኒያ ባንክ (BOA):</b> <code>{boa_acc}</code>\n"
        f"👤 <b>ስም:</b> {boa_holder}\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"{tail}"
    )


def get_optimized_welcome_photos() -> list[str]:
    raw_images = [
        "IMG_1591 (1)",
        "Side-by-Side Fitness Progress Photo",
        "Before and After_ Street to Gym",
    ]
    resolved = []
    for base in raw_images:
        opt_path = os.path.join(settings.resolved_image_dir, f"{base}_opt.jpg")
        if os.path.exists(opt_path):
            resolved.append(opt_path)
            continue
        for ext in [".jpg", ".JPG", ".png", ".PNG"]:
            raw_path = os.path.join(settings.resolved_image_dir, f"{base}{ext}")
            if os.path.exists(raw_path):
                try:
                    from PIL import Image
                    im = Image.open(raw_path).convert("RGB")
                    im.thumbnail((1280, 1280))
                    im.save(opt_path, "JPEG", quality=85, optimize=True)
                    resolved.append(opt_path)
                except Exception as e:
                    logger.warning(f"Failed to optimize {raw_path}: {e}")
                    resolved.append(raw_path)
                break
    return resolved


# ---------------------------------------------------------
# Core Helper: Start New Visitor Onboarding Flow (Instant Cached Media)
# ---------------------------------------------------------
async def start_new_visitor_flow(message: Message, bot: Bot):
    global _cached_welcome_file_ids
    chat_id = message.chat.id
    fire_typing(bot, chat_id)

    caption = (
        "ሰላም! <b>ብሩክታዊት ፍቅሬ</b> ነኝ፣ ISSA-certified አሰልጣኝ (4+ ዓመት ልምድ፣ ከ <b>140K+</b> በላይ ቤተሰቦች) 🏋️‍♀️✨\n\n"
        "ብዙ ሰዎች ጂም ገብተው ቢለፉም ለውጥ የማያዩት ሰነፍ ሆነው ሳይሆን፣ ያለ ግልጽ እቅድ ስለሚሰሩ እና "
        "ለሰውነታቸው የማይሆን መንገድ ስለሚሞክሩ ነው።\n\n"
        "የእኔ ስራ በመስታወት እና በልብስ የሚታይ እውነተኛ ለውጥ እንድታመጡ መምራት ነው፣ Fat Loss ይሁን Booty ወይም Muscle Gain።\n\n"
        "ለሰውነታችሁ የሚሄድ የ <b>8 ሳምንት ፕላን</b> እንድናወጣ፣ 5 አጫጭር ጥያቄዎችን እንመልስ 👇"
    )

    valid_photos = get_optimized_welcome_photos()
    step1_prompt = "▰▱▱▱▱\n<b>Step 1/5፦ ጾታ ምረጡ 👇</b>"

    if _cached_welcome_file_ids and len(_cached_welcome_file_ids) == len(valid_photos):
        try:
            media_group = [
                InputMediaPhoto(media=_cached_welcome_file_ids[0], caption=caption, parse_mode="HTML")
            ] + [
                InputMediaPhoto(media=fid) for fid in _cached_welcome_file_ids[1:]
            ]
            await bot.send_media_group(chat_id=chat_id, media=media_group)
            await bot.send_message(chat_id, step1_prompt, parse_mode="HTML", reply_markup=get_gender_keyboard())
            return
        except Exception as e:
            logger.warning(f"Cached media group send failed ({e}), re-uploading files.")
            _cached_welcome_file_ids = []

    if len(valid_photos) >= 2:
        try:
            media_group = []
            for idx, p in enumerate(valid_photos):
                if idx == 0:
                    media_group.append(InputMediaPhoto(media=FSInputFile(p), caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=FSInputFile(p)))
            sent_msgs = await bot.send_media_group(chat_id=chat_id, media=media_group)
            if sent_msgs:
                _cached_welcome_file_ids = [m.photo[-1].file_id for m in sent_msgs if m.photo]
            await bot.send_message(chat_id, step1_prompt, parse_mode="HTML", reply_markup=get_gender_keyboard())
            return
        except Exception as e:
            logger.error(f"Error sending media group: {e}")

    if len(valid_photos) >= 1:
        await bot.send_photo(chat_id, photo=FSInputFile(valid_photos[0]), caption=caption, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML")

    await bot.send_message(chat_id, step1_prompt, parse_mode="HTML", reply_markup=get_gender_keyboard())


# ---------------------------------------------------------
# Step 0: /reset -> Instant Hard Reset
# ---------------------------------------------------------
@router.message(Command("reset"))
async def handle_reset(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    await asyncio.gather(
        state.clear(),
        db.reset_athlete_onboarding(user_id),
    )
    await message.answer(
        "🔄 <b>ፕሮፋይል ከዜሮ ተጀምሯል!</b>\nከመጀመሪያ እንጀምር 👇",
        parse_mode="HTML",
        reply_markup=get_user_main_menu(),
    )
    await start_new_visitor_flow(message, bot)


# ---------------------------------------------------------
# Step 1: /start -> Fast Smart Welcome / State Resumption
# ---------------------------------------------------------
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    full_name = user.full_name or "አባል"
    username = user.username

    existing_athlete = await db.get_athlete(user.id)
    if existing_athlete:
        # Refresh last_interaction asynchronously so user never waits for an UPDATE
        asyncio.create_task(db.upsert_athlete(user.id, full_name, username))

        reply_kb = get_user_main_menu()
        is_fem = existing_athlete.get("gender") == "FEMALE"
        state_code = existing_athlete.get("onboarding_state", "START")

        # Single fast query for latest order status
        async with db.pool.acquire() as conn:
            latest_order = await conn.fetchrow(
                "SELECT sku, status, receipt_file_id FROM orders WHERE athlete_id = $1 ORDER BY created_at DESC LIMIT 1;",
                user.id,
            )

        if latest_order and latest_order["status"] in ("VERIFIED", "DELIVERED"):
            plan_label = html.escape(format_plan_name(latest_order["sku"]))
            welcome_back = (
                "ሰላም ቆንጆዬ! 👋 እንኳን ተመልሰሽ መጣሽ!\n\n"
                f"<b>{plan_label}</b> ፕላንሽ ንቁ ነው። "
                "ከታች <b>'📝 ሳምንታዊ Check-in'</b> የሚለውን ነክተሽ የዚህን ሳምንት ሚዛንሽን መዝግቢ! 🔥"
                if is_fem else
                "ሰላም ወንድሜ! 👋 እንኳን ተመልሰህ መጣህ!\n\n"
                f"<b>{plan_label}</b> ፕላንህ ንቁ ነው። "
                "ከታች <b>'📝 ሳምንታዊ Check-in'</b> የሚለውን ነክተህ የዚህን ሳምንት ሚዛንህን መዝግብ! 💪"
            )
            await message.answer(welcome_back, parse_mode="HTML", reply_markup=reply_kb)
            await message.answer(
                "የፕላንሽ አማራጮች 👇" if is_fem else "የፕላንህ አማራጮች 👇",
                reply_markup=get_athlete_plan_keyboard(has_active_order=True),
            )
            return

        if latest_order and latest_order["status"] == "PENDING" and latest_order["receipt_file_id"]:
            wait_text = (
                "ሰላም ቆንጆዬ! 👋 የላክሽው የክፍያ ደረሰኝ እየታየ ነው። "
                "በጥቂት ደቂቃዎች ውስጥ አረጋግጬ ፕላንሽን በ PDF እልክልሻለሁ ⏳"
                if is_fem else
                "ሰላም ወንድሜ! 👋 የላክኸው የክፍያ ደረሰኝ እየታየ ነው። "
                "በጥቂት ደቂቃዎች ውስጥ አረጋግጬ ፕላንህን በ PDF እልክልሃለሁ ⏳"
            )
            await message.answer(wait_text, parse_mode="HTML", reply_markup=reply_kb)
            return

        if state_code == "CHECKOUT_PITCHED":
            resume_text = (
                "ሰላም ቆንጆዬ! 👋 እንኳን ተመልሰሽ መጣሽ!\n\n"
                "ላንቺ የተዘጋጀው የ 8-ሳምንቱ ፕላን ዝግጁ ነው። ክፍያውን እንደፈጸምሽ ደረሰኙን እዚህ ላኪልኝ 👇"
                if is_fem else
                "ሰላም ወንድሜ! 👋 እንኳን ተመልሰህ መጣህ!\n\n"
                "ላንተ የተዘጋጀው የ 8-ሳምንቱ ፕላን ዝግጁ ነው። ክፍያውን እንደፈጸምክ ደረሰኙን እዚህ ላክልኝ 👇"
            )
            resume_kb = get_resume_keyboard("CHECKOUT_PITCHED", settings.CBE_ACCOUNT, settings.BOA_ACCOUNT, is_female=is_fem)
            await message.answer(resume_text, parse_mode="HTML", reply_markup=resume_kb)
            return

        if state_code in ("GENDER_SET", "AGE_SET", "WEIGHT_SET", "GOAL_SET", "SPLIT_SET", "DIAGNOSTIC_READY"):
            resume_text = (
                "ሰላም ቆንጆዬ! 👋 ባለፈው የጀመርነውን ፕላን እንጨርስ?\n\n"
                "ከታች <b>'➡️ የቀረኝን ጥያቄ ልመልስ'</b> የሚለውን ንኪ 👇"
                if is_fem else
                "ሰላም ወንድሜ! 👋 ባለፈው የጀመርነውን ፕላን እንጨርስ?\n\n"
                "ከታች <b>'➡️ የቀረኝን ጥያቄ ልመልስ'</b> የሚለውን ንካ 👇"
            )
            resume_kb = get_resume_keyboard("ONBOARDING", settings.CBE_ACCOUNT, settings.BOA_ACCOUNT, is_female=is_fem)
            await message.answer(resume_text, parse_mode="HTML", reply_markup=resume_kb)
            return
    else:
        asyncio.create_task(db.upsert_athlete(user.id, full_name, username))

    await start_new_visitor_flow(message, bot)


# ---------------------------------------------------------
# Step 2: Gender Selection -> Ask Age (Step 2/5)
# ---------------------------------------------------------
async def prompt_age(chat_id: int, is_female: bool, bot: Bot, state: FSMContext):
    fire_typing(bot, chat_id)
    await asyncio.sleep(0.25)

    if is_female:
        text = (
            "ግልጽ እንሁን ቆንጆዬ፣ ያለ ትክክለኛ ፕሮግራም መልፋት ውጤት አያመጣም።\n\n"
            "▰▰▱▱▱\n"
            "<b>Step 2/5፦ ስንት ዓመትሽ ነው? 🎯</b>\n\n"
            "<i>(እድሜሽን ስናውቅ ሰውነትሽ ምን ያህል ጫና እና እረፍት እንደሚፈልግ እንለያለን)</i>"
        )
    else:
        text = (
            "ግልጽ እንሁን ወንድሜ፣ ያለ አቅጣጫ ጂም መመላለስ ጊዜ ማጥፋት ብቻ ነው።\n\n"
            "▰▰▱▱▱\n"
            "<b>Step 2/5፦ ስንት ዓመትህ ነው? 🎯</b>\n\n"
            "<i>(እድሜህን ስናውቅ የስልጠናውን ጫና እና የማገገሚያ ጊዜህን በልክ እንይዛለን)</i>"
        )

    await state.set_state(IntakeFSM.age)
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_age_keyboard())


@router.callback_query(F.data.startswith("gender:"))
async def handle_gender_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # Answer immediately (0ms spinner stop, prevents 'query is too old')
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    gender = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    fire_typing(bot, chat_id)

    await db.update_athlete_fields(user_id, gender=gender, onboarding_state="GENDER_SET")
    await prompt_age(chat_id, gender == "FEMALE", bot, state)


# ---------------------------------------------------------
# Step 3: Age -> Ask Weight (Step 3/5)
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("age:"))
async def handle_age_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    raw_age = callback.data.split(":", 1)[1]
    age_val, age_label = parse_age_callback(raw_age)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    fire_typing(bot, chat_id)

    athlete = await db.update_athlete_fields(
        user_id,
        age=age_val,
        age_range=age_label,
        onboarding_state="AGE_SET",
    )
    await prompt_weight(chat_id, user_id, bot, state, athlete=athlete)


@router.message(IntakeFSM.age)
async def handle_age_text(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text, bot)
        return

    user_id = message.from_user.id
    athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    age_val = extract_age(text)
    if not age_val:
        err = (
            "እድሜሽን በቁጥር ብቻ ላኪልኝ (ለምሳሌ 24) ወይም ከላይ ያሉትን ቁልፎች ተጫኚ 👇"
            if is_female else
            "እድሜህን በቁጥር ብቻ ላክልኝ (ለምሳሌ 26) ወይም ከላይ ያሉትን ቁልፎች ተጫን 👇"
        )
        await message.answer(err)
        return

    athlete = await db.update_athlete_fields(
        user_id,
        age=age_val,
        age_range=str(age_val),
        onboarding_state="AGE_SET",
    )
    await prompt_weight(message.chat.id, user_id, bot, state, athlete=athlete)


async def prompt_weight(
    chat_id: int,
    user_id: int,
    bot: Bot,
    state: FSMContext,
    athlete: Optional[dict] = None,
):
    fire_typing(bot, chat_id)
    if athlete is None:
        athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    if is_female:
        text = (
            "ጥሩ፣ አሁን ከሰውነትሽ አቅም ጋር የሚሄድ እቅድ እንገንባ።\n\n"
            "▰▰▰▱▱\n"
            "<b>Step 3/5፦ አሁን ክብደትሽ ስንት ኪሎ ነው? ⚖️</b>\n\n"
            "<i>(የቀን ካሎሪ እና ፕሮቲን ለማወቅ ይረዳናል)</i>"
        )
    else:
        text = (
            "ጥሩ፣ አሁን ከሰውነትህ አቅም ጋር የሚሄድ እቅድ እንገንባ።\n\n"
            "▰▰▰▱▱\n"
            "<b>Step 3/5፦ አሁን ክብደትህ ስንት ኪሎ ነው? ⚖️</b>\n\n"
            "<i>(የቀን ካሎሪ እና ፕሮቲን ለማወቅ ይረዳናል)</i>"
        )
    await state.set_state(IntakeFSM.weight)
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_weight_keyboard())


# ---------------------------------------------------------
# Step 4: Weight -> Primary Goal (Step 4/5)
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("weight:"))
async def handle_weight_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    weight_val = float(callback.data.split(":")[1])
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    fire_typing(bot, chat_id)

    athlete, _ = await asyncio.gather(
        db.update_athlete_fields(user_id, weight_kg=weight_val, onboarding_state="WEIGHT_SET"),
        state.clear(),
    )
    await prompt_goal(chat_id, user_id, bot, athlete=athlete)


@router.message(IntakeFSM.weight)
async def handle_weight_text(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text, bot)
        return

    user_id = message.from_user.id
    athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    weight_val = extract_weight(text)
    if not weight_val:
        err = (
            "ክብደትሽን በኪሎግራም በቁጥር ላኪ (ለምሳሌ 62) 👇"
            if is_female else
            "ክብደትህን በኪሎግራም በቁጥር ላክ (ለምሳሌ 70) 👇"
        )
        await message.answer(err)
        return

    athlete, _ = await asyncio.gather(
        db.update_athlete_fields(user_id, weight_kg=weight_val, onboarding_state="WEIGHT_SET"),
        state.clear(),
    )
    await prompt_goal(message.chat.id, user_id, bot, athlete=athlete)


async def prompt_goal(chat_id: int, user_id: int, bot: Bot, athlete: Optional[dict] = None):
    fire_typing(bot, chat_id)
    if athlete is None:
        athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    if is_female:
        text = (
            "ተመዝግቧል። ሚዛን ላይ ያለ ቁጥር ብቻውን ለውጥ አይደለም፣ ዋናው በልብስና በመስታወት የሚታይ ቅርጽ ነው።\n\n"
            "▰▰▰▰▱\n"
            "<b>Step 4/5፦ በ 8 ሳምንት ውስጥ ዋና ግብሽ ምንድን ነው? 🏆</b>\n\n"
            "<i>(ላንቺ የሚቀድመውን አንዱን ምረጪ)</i>"
        )
    else:
        text = (
            "ተመዝግቧል። ሚዛን ላይ ያለ ቁጥር ብቻውን ለውጥ አይደለም፣ ዋናው በልብስና በመስታወት የሚታይ ጡንቻ ነው።\n\n"
            "▰▰▰▰▱\n"
            "<b>Step 4/5፦ በ 8 ሳምንት ውስጥ ዋና ግብህ ምንድን ነው? 🏆</b>\n\n"
            "<i>(ላንተ የሚቀድመውን አንዱን ምረጥ)</i>"
        )
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_goal_keyboard(is_female))


# ---------------------------------------------------------
# Step 5: Primary Goal -> Weekly Gym Frequency (Step 5/5)
# ---------------------------------------------------------
async def prompt_frequency(chat_id: int, user_id: int, bot: Bot, athlete: Optional[dict] = None):
    fire_typing(bot, chat_id)
    if athlete is None:
        athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    if is_female:
        text = (
            "ግልጽ ነው። በሳምንት 7 ቀን መልፋት አያስፈልግም፣ ዋናው ወጥ ሆኖ ትክክለኛውን ፎርም መያዝ ነው።\n\n"
            "▰▰▰▰▰\n"
            "<b>Step 5/5፦ በሳምንት ስንት ቀን ጂም መሄድ ትችያለሽ? 🗓️</b>\n\n"
            "<i>(መገኘት የምትችይውን ትክክለኛ ቀን ምረጪ፣ እረፍትም የስልጠናው አካል ነው)</i>"
        )
    else:
        text = (
            "ግልጽ ነው። በሳምንት 7 ቀን መልፋት አያስፈልግም፣ ዋናው ወጥ ሆኖ ትክክለኛውን ፎርም መያዝ ነው።\n\n"
            "▰▰▰▰▰\n"
            "<b>Step 5/5፦ በሳምንት ስንት ቀን ጂም መሄድ ትችላለህ? 🗓️</b>\n\n"
            "<i>(መገኘት የምትችለውን ትክክለኛ ቀን ምረጥ፣ እረፍትም የስልጠናው አካል ነው)</i>"
        )
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_frequency_keyboard())


@router.callback_query(F.data.startswith("goal:"))
async def handle_goal_choice(callback: CallbackQuery, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    goal = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    fire_typing(bot, chat_id)

    athlete = await db.update_athlete_fields(user_id, primary_goal=goal, onboarding_state="GOAL_SET")
    await prompt_frequency(chat_id, user_id, bot, athlete=athlete)


# ---------------------------------------------------------
# Deliberate Calibration Loop -> VIP Member Profile Card -> Commitment
# ---------------------------------------------------------
async def show_profile_and_commitment(chat_id: int, user_id: int, athlete: dict, bot: Bot, animate: bool = True):
    is_female = athlete.get("gender") == "FEMALE"
    days = athlete.get("days_per_week") or 4
    if days not in (3, 4):
        days = 4

    calib_msg = None
    if animate:
        calib_msg = await bot.send_message(
            chat_id,
            "⚙️ <b>መረጃሽን እያየሁ ነው...</b>" if is_female else "⚙️ <b>መረጃህን እያየሁ ነው...</b>",
            parse_mode="HTML",
        )

        steps = [
            (
                f"📊 የ {days} ቀን የጂም ፕላንሽን እያዘጋጀሁ ነው..."
                if is_female else
                f"📊 የ {days} ቀን የጂም ፕላንህን እያዘጋጀሁ ነው..."
            ),
            (
                "🥗 በቀን የሚያስፈልግሽን ካሎሪ እና ፕሮቲን እያሰላሁ ነው..."
                if is_female else
                "🥗 በቀን የሚያስፈልግህን ካሎሪ እና ፕሮቲን እያሰላሁ ነው..."
            ),
            (
                "📐 ለግብሽ የሚሆኑ እንቅስቃሴዎችን እና RIR መለኪያ በመምረጥ ላይ..."
                if is_female else
                "📐 ለግብህ የሚሆኑ እንቅስቃሴዎችን እና RIR መለኪያ በመምረጥ ላይ..."
            ),
            (
                "✨ <b>መታወቂያ ካርድሽ ዝግጁ ነው 👇</b>"
                if is_female else
                "✨ <b>መታወቂያ ካርድህ ዝግጁ ነው 👇</b>"
            ),
        ]
        for step in steps:
            await asyncio.sleep(1.3)
            try:
                await calib_msg.edit_text(step, parse_mode="HTML")
            except Exception:
                pass
        await asyncio.sleep(0.8)

    diagnostic_card = generate_athlete_diagnostic_card(athlete, user_id)

    if calib_msg:
        try:
            await calib_msg.edit_text(diagnostic_card, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, diagnostic_card, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, diagnostic_card, parse_mode="HTML")

    # Notify admin group asynchronously so user response never waits for external group API call
    if animate and settings.ADMIN_NEWUSER_GID:
        safe_name = html.escape(athlete.get("full_name") or "New Member")
        username = athlete.get("username")
        safe_username = f"@{html.escape(username)}" if username else "No Username"
        gender_val = "👩 ሴት (Female)" if is_female else "👨 ወንድ (Male)"
        age_val = html.escape(format_age_display(athlete))
        weight_val = athlete.get("weight_kg", "N/A")
        raw_goal = athlete.get("primary_goal", "BOOTY_CURVES")
        sku_assigned, goal_display = _resolve_sku_and_goal(is_female, raw_goal, days)

        admin_notify_msg = (
            "⚡️ <b>NEW MEMBER REGISTERED</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {safe_username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"🧬 <b>Gender:</b> {gender_val}\n"
            f"🎂 <b>Age:</b> {age_val}\n"
            f"⚖️ <b>Weight:</b> {weight_val} kg\n"
            f"🎯 <b>Goal:</b> {html.escape(goal_display)}\n"
            f"📅 <b>Split:</b> {days}x / week\n"
            f"📦 <b>Plan:</b> {html.escape(format_plan_name(sku_assigned))}\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔥 <b>The Birukti movement is growing...</b>"
        )
        fire_send(bot, settings.ADMIN_NEWUSER_GID, admin_notify_msg, parse_mode="HTML")

    await asyncio.sleep(1.2 if animate else 0.4)

    if is_female:
        commitment_text = (
            "ይሄንን ስሌት ወደ እውነተኛ ለውጥ ለመቀየር ፍጹም መሆን አያስፈልግም፣ ወጥ ሆነሽ አለማቆም ብቻ ነው።\n\n"
            "አንድ ቀን ቢያልፍሽም ሳታቆሚ ከኔ ጋር 8ቱን ሳምንት እስክንጨርስ ድረስ ለራስሽ ቃል ትገቢያለሽ? 🔥"
        )
    else:
        commitment_text = (
            "ይሄንን ስሌት ወደ እውነተኛ ለውጥ ለመቀየር ፍጹም መሆን አያስፈልግም፣ ወጥ ሆነህ አለማቆም ብቻ ነው።\n\n"
            "አንድ ቀን ቢያልፍህም ሳታቆም ከኔ ጋር 8ቱን ሳምንት እስክንጨርስ ድረስ ለራስህ ቃል ትገባለህ? 🔥"
        )
    await bot.send_message(chat_id, commitment_text, parse_mode="HTML", reply_markup=get_commitment_keyboard())


@router.callback_query(F.data.startswith("freq:"))
async def handle_freq_choice(callback: CallbackQuery, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    days = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    athlete = await db.update_athlete_fields(
        user_id,
        days_per_week=days,
        experience_level="INTERMEDIATE",
        onboarding_state="DIAGNOSTIC_READY",
    )
    await show_profile_and_commitment(chat_id, user_id, athlete, bot, animate=True)


# ---------------------------------------------------------
# Commitment Micro-Yes -> Free PDF Reward (if present) -> 8-Week Pitch (CBE/BOA)
# ---------------------------------------------------------
@router.callback_query(F.data == "commit_YES")
async def handle_commitment(callback: CallbackQuery, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    athlete = await db.get_athlete(user_id)

    is_female = bool(athlete and athlete.get("gender") == "FEMALE")
    raw_goal = athlete.get("primary_goal", "BOOTY_CURVES") if athlete else "BOOTY_CURVES"
    days = athlete.get("days_per_week", 4) if athlete else 4
    if days not in (3, 4):
        days = 4

    free_guide_path = os.path.join(settings.resolved_pdf_dir, "Biruktawit_Fitness_Foundation_Guide.pdf")

    if os.path.exists(free_guide_path):
        fire_typing(bot, chat_id, ChatAction.UPLOAD_DOCUMENT)
        if is_female:
            free_caption = (
                "🎁 <b>ይሄ ላንቺ የላኩት ነፃ የፎርም መመሪያ ነው (Foundation PDF) 📖</b>\n\n"
                "ቃል ስለገባሽ ደስ ብሎኛል፣ ጂም ስትገቢ ሳትጎጂ ትክክለኛውን ጡንቻ የምታሰሪበትን መመሪያ ከታች አውርጂው።\n\n"
                "አሁን ደግሞ የሙሉውን 8-ሳምንት ፕላንሽን እንክፈት 👇"
            )
        else:
            free_caption = (
                "🎁 <b>ይሄ ላንተ የላኩት ነፃ የፎርም መመሪያ ነው (Foundation PDF) 📖</b>\n\n"
                "ቃል ስለገባህ ደስ ብሎኛል፣ ጂም ስትገባ ሳትጎዳ ትክክለኛውን ጡንቻ የምታሰራበትን መመሪያ ከታች አውርደው።\n\n"
                "አሁን ደግሞ የሙሉውን 8-ሳምንት ፕላንህን እንክፈት 👇"
            )
        await bot.send_document(
            chat_id,
            document=FSInputFile(free_guide_path),
            caption=free_caption,
            parse_mode="HTML",
            reply_markup=get_user_main_menu(),
        )
        await asyncio.sleep(0.8)
    else:
        ready_msg = (
            "ጥሩ ቆንጆዬ! ቃል ስለገባሽ አሁን ባለ 20 ገጹን የ 8-ሳምንት ፕላንሽን እንክፈት 👇"
            if is_female else
            "ጥሩ ወንድሜ! ቃል ስለገባህ አሁን ባለ 20 ገጹን የ 8-ሳምንት ፕላንህን እንክፈት 👇"
        )
        await bot.send_message(chat_id, ready_msg, parse_mode="HTML", reply_markup=get_user_main_menu())

    sku, goal_name = _resolve_sku_and_goal(is_female, raw_goal, days)
    await asyncio.gather(
        _get_or_create_pending_order(user_id, sku),
        db.update_athlete_fields(user_id, onboarding_state="CHECKOUT_PITCHED"),
    )

    pitch_text = _build_pitch_text(is_female, goal_name)
    await bot.send_message(chat_id, pitch_text, parse_mode="HTML", reply_markup=get_offer_cta_keyboard(settings.DEFAULT_PRICE_ETB))


# ---------------------------------------------------------
# Stage 2: Dedicated Payment Page (When clicking "💳 ክፍያ ፈጽም")
# ---------------------------------------------------------
@router.callback_query(F.data == "open_payment_page")
async def handle_open_payment_page(callback: CallbackQuery, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    athlete = await db.get_athlete(user_id)

    if not athlete or not athlete.get("gender") or not athlete.get("primary_goal"):
        await start_new_visitor_flow(callback.message, bot)
        return

    is_female = athlete.get("gender") == "FEMALE"
    raw_goal = athlete.get("primary_goal", "BOOTY_CURVES")
    days = athlete.get("days_per_week") or 4
    sku, _ = _resolve_sku_and_goal(is_female, raw_goal, days)

    await asyncio.gather(
        _get_or_create_pending_order(user_id, sku),
        db.update_athlete_fields(user_id, onboarding_state="CHECKOUT_PITCHED"),
    )

    pay_text = _build_payment_page_text(is_female, sku)
    payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.BOA_ACCOUNT)
    await bot.send_message(chat_id, pay_text, parse_mode="HTML", reply_markup=payment_kb)


# ---------------------------------------------------------
# Buy Now Callback (From Menu -> "🔥 8-ሳምንቱን ልጀምር")
# ---------------------------------------------------------
@router.callback_query(F.data == "buy_now")
async def handle_buy_now(callback: CallbackQuery, state: FSMContext, bot: Bot):
    asyncio.create_task(safe_answer(callback))

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    athlete = await db.get_athlete(user_id)

    if not athlete or not athlete.get("gender") or not athlete.get("primary_goal"):
        await start_new_visitor_flow(callback.message, bot)
        return

    is_female = athlete.get("gender") == "FEMALE"
    raw_goal = athlete.get("primary_goal", "BOOTY_CURVES")
    days = athlete.get("days_per_week") or 4
    sku, _ = _resolve_sku_and_goal(is_female, raw_goal, days)

    await asyncio.gather(
        _get_or_create_pending_order(user_id, sku),
        db.update_athlete_fields(user_id, onboarding_state="CHECKOUT_PITCHED"),
    )

    pay_text = _build_payment_page_text(is_female, sku)
    payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.BOA_ACCOUNT)
    await bot.send_message(chat_id, pay_text, parse_mode="HTML", reply_markup=payment_kb)


# ---------------------------------------------------------
# State Resumption & Restart Callbacks
# ---------------------------------------------------------
@router.callback_query(F.data == "restart_flow")
async def handle_restart_flow(callback: CallbackQuery, state: FSMContext, bot: Bot):
    asyncio.create_task(safe_answer(callback, "ከመጀመሪያ ተጀምሯል!"))
    asyncio.create_task(safe_delete(callback.message))

    user_id = callback.from_user.id
    await asyncio.gather(
        state.clear(),
        db.reset_athlete_onboarding(user_id),
    )
    await start_new_visitor_flow(callback.message, bot)


@router.callback_query(F.data == "resume_onboarding")
async def handle_resume_onboarding(callback: CallbackQuery, state: FSMContext, bot: Bot):
    asyncio.create_task(safe_answer(callback))
    asyncio.create_task(safe_delete(callback.message))

    user_id = callback.from_user.id
    athlete = await db.get_athlete(user_id)
    if not athlete:
        await start_new_visitor_flow(callback.message, bot)
        return

    state_code = athlete.get("onboarding_state", "START")
    is_female = athlete.get("gender") == "FEMALE"
    chat_id = callback.message.chat.id

    if state_code == "GENDER_SET":
        await prompt_age(chat_id, is_female, bot, state)
    elif state_code == "AGE_SET":
        await prompt_weight(chat_id, user_id, bot, state, athlete=athlete)
    elif state_code == "WEIGHT_SET":
        await prompt_goal(chat_id, user_id, bot, athlete=athlete)
    elif state_code == "GOAL_SET":
        await prompt_frequency(chat_id, user_id, bot, athlete=athlete)
    elif state_code == "DIAGNOSTIC_READY":
        await show_profile_and_commitment(chat_id, user_id, athlete, bot, animate=False)
    else:
        await start_new_visitor_flow(callback.message, bot)


# ---------------------------------------------------------
# Receipt Upload Guidance Callback
# ---------------------------------------------------------
@router.callback_query(F.data == "send_receipt_guide")
async def handle_send_receipt_guide(callback: CallbackQuery):
    asyncio.create_task(safe_answer(callback))
    user_id = callback.from_user.id
    athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    if is_female:
        guide = (
            "📸 <b>ደረሰኝ አላላክ፦</b>\n\n"
            "1. በ CBE ወይም በ BOA የከፈልሽበትን ማረጋገጫ Screenshot አድርጊ።\n"
            "2. ልክ እንደ ፎቶ ቀጥታ ወደዚህ ቻት ላኪው።\n"
            "3. በ 1 እስከ 3 ደቂቃ ውስጥ አረጋግጬ ባለ 20 ገጹን ፕላንሽን PDF እልክልሻለሁ 🚀"
        )
    else:
        guide = (
            "📸 <b>ደረሰኝ አላላክ፦</b>\n\n"
            "1. በ CBE ወይም በ BOA የከፈልክበትን ማረጋገጫ Screenshot አድርግ።\n"
            "2. ልክ እንደ ፎቶ ቀጥታ ወደዚህ ቻት ላከው።\n"
            "3. በ 1 እስከ 3 ደቂቃ ውስጥ አረጋግጬ ባለ 20 ገጹን ፕላንህን PDF እልክልሃለሁ 🚀"
        )
    await callback.message.answer(guide, parse_mode="HTML")


# ---------------------------------------------------------
# Persistent Menu Button Routing
# ---------------------------------------------------------
@router.message(F.text.in_(MENU_TEXTS))
async def handle_menu_click(message: Message, bot: Bot):
    await route_menu_action(message, message.text, bot)


async def route_menu_action(message: Message, text: str, bot: Bot = None):
    user_id = message.from_user.id
    athlete = await db.get_athlete(user_id)

    if not athlete:
        athlete = await db.upsert_athlete(user_id, message.from_user.full_name or "አባል", message.from_user.username)

    is_female = athlete.get("gender") == "FEMALE"
    has_gender = athlete.get("gender") in ("FEMALE", "MALE")

    if "የኔ ፕላን" in text or "የእኔ ፕሮግራም" in text:
        async with db.pool.acquire() as conn:
            verified_order = await conn.fetchrow(
                "SELECT sku FROM orders WHERE athlete_id = $1 AND status IN ('VERIFIED', 'DELIVERED') ORDER BY created_at DESC LIMIT 1;",
                user_id,
            )

        if verified_order:
            plan_label = html.escape(format_plan_name(verified_order["sku"]))
            if is_female:
                plan_text = (
                    "🏋️‍♀️ <b>አክቲቭ የሆነው የ 8-ሳምንት ፕላንሽ</b>\n\n"
                    f"• ፕላን: <b>{plan_label}</b>\n"
                    "• ሁኔታ: <b>(ACTIVE)</b>\n\n"
                    "እድገትሽን ለመመዝገብ <b>'📝 ሳምንታዊ Check-in'</b> የሚለውን ንኪ 👇"
                )
            else:
                plan_text = (
                    "🏋️‍♀️ <b>አክቲቭ የሆነው የ 8-ሳምንት ፕላንህ</b>\n\n"
                    f"• ፕላን: <b>{plan_label}</b>\n"
                    "• ሁኔታ: <b>(ACTIVE)</b>\n\n"
                    "እድገትህን ለመመዝገብ <b>'📝 ሳምንታዊ Check-in'</b> የሚለውን ንካ 👇"
                )
            await message.answer(plan_text, parse_mode="HTML", reply_markup=get_athlete_plan_keyboard(has_active_order=True))
        else:
            if not has_gender:
                no_plan_text = "ገና የተከፈተ ፕላን የለም። መጀመሪያ /start ብለው 5ቱን ጥያቄዎች ይምረጡ 👇"
            elif is_female:
                no_plan_text = (
                    "ገና የተረጋገጠ ፕላንሽ አልተከፈተም።\n\n"
                    "የ 8-ሳምንቱን ፕላንሽን ለመክፈት ከታች ያለውን ቁልፍ ተጫኚ 👇"
                )
            else:
                no_plan_text = (
                    "ገና የተረጋገጠ ፕላንህ አልተከፈተም።\n\n"
                    "የ 8-ሳምንቱን ፕላንህን ለመክፈት ከታች ያለውን ቁልፍ ተጫን 👇"
                )
            await message.answer(no_plan_text, parse_mode="HTML", reply_markup=get_athlete_plan_keyboard(has_active_order=False))

    elif "ክፍያ" in text or "ደረሰኝ" in text:
        cbe_acc = html.escape(settings.CBE_ACCOUNT)
        cbe_holder = html.escape(settings.CBE_ACCOUNT_HOLDER)
        boa_acc = html.escape(settings.BOA_ACCOUNT)
        boa_holder = html.escape(settings.BOA_ACCOUNT_HOLDER)

        if has_gender and is_female:
            tail = "ክፍያ እንደፈጸምሽ ደረሰኙን Screenshot አድርገሽ እዚህ ላኪልኝ!"
        elif has_gender:
            tail = "ክፍያ እንደፈጸምክ ደረሰኙን Screenshot አድርገህ እዚህ ላክልኝ!"
        else:
            tail = "ክፍያ እንደፈጸሙ ደረሰኙን Screenshot አድርገው እዚህ ይላኩ!"

        payment_text = (
            "💳 <b>የመክፈያ ባንክ አካውንቶች፦</b>\n\n"
            f"💰 <b>ዋጋ:</b> <code>{settings.DEFAULT_PRICE_ETB} ብር</code>\n\n"
            f"🏦 <b>ንግድ ባንክ (CBE):</b> <code>{cbe_acc}</code>\n"
            f"👤 <b>ስም:</b> {cbe_holder}\n\n"
            f"🏦 <b>አቢሲኒያ ባንክ (BOA):</b> <code>{boa_acc}</code>\n"
            f"👤 <b>ስም:</b> {boa_holder}\n\n"
            f"{tail}"
        )
        payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.BOA_ACCOUNT)
        await message.answer(payment_text, parse_mode="HTML", reply_markup=payment_kb)

    elif "ነፃ መመሪያ" in text:
        free_guide_path = os.path.join(settings.resolved_pdf_dir, "Biruktawit_Fitness_Foundation_Guide.pdf")
        if os.path.exists(free_guide_path):
            if has_gender and is_female:
                free_msg = (
                    "🎁 <b>የብሩክታዊት ነፃ የፎርም መመሪያ (PDF)</b>\n\n"
                    "ጂም ስትገቢ ሳትጎጂ ትክክለኛውን ጡንቻ ለማሰራት የሚረዱ ህጎች አሉበት፣ አውርደሽ ተመልከቺው 👇"
                )
            elif has_gender:
                free_msg = (
                    "🎁 <b>የብሩክታዊት ነፃ የፎርም መመሪያ (PDF)</b>\n\n"
                    "ጂም ስትገባ ሳትጎዳ ትክክለኛውን ጡንቻ ለማሰራት የሚረዱ ህጎች አሉበት፣ አውርደህ ተመልከተው 👇"
                )
            else:
                free_msg = "🎁 <b>የብሩክታዊት ነፃ የፎርም መመሪያ (PDF)</b>\n\nአውርደው ይመልከቱት 👇"
            await message.answer_document(document=FSInputFile(free_guide_path), caption=free_msg, parse_mode="HTML")
        else:
            await message.answer(
                "🎁 ነፃው የፎርም መመሪያ PDF በዝግጅት ላይ ነው፣ በቅርቡ እዚህ ይለቀቃል!",
                parse_mode="HTML",
            )

    elif "ስለ ብሩክቲ" in text:
        handle = html.escape(settings.CREATOR_HANDLE)
        support = html.escape(settings.SUPPORT_BOT_USERNAME)
        about_text = (
            "ℹ️ <b>ስለ Coach Biruktawit Fikre</b>\n\n"
            "ሰላም! ብሩክታዊት ፍቅሬ ነኝ፣ ISSA-certified የአካል ብቃት አሰልጣኝ።\n\n"
            "ዋናው ስራዬ ለሴቶች ዳሌና መቀመጫን ማሳደግ፣ ወገብን ማጥበብና ስብ መቀነስ ሲሆን፣ "
            "ለወንዶች ደግሞ የጡንቻ ግንባታና ቦርጭን የማጥፋት ተግባራዊ የ 8-ሳምንት ፕላኖችን ማዘጋጀት ነው።\n\n"
            f"📩 ቀጥታ Support: @{support} ({handle})"
        )
        await message.answer(about_text, parse_mode="HTML", reply_markup=get_support_keyboard())


# ---------------------------------------------------------
# Post-Purchase Weekly Check-in Flow (Sunday Empty-Stomach Tracker)
# ---------------------------------------------------------
@router.callback_query(F.data == "checkin:new")
async def handle_start_checkin(callback: CallbackQuery, state: FSMContext):
    asyncio.create_task(safe_answer(callback))

    user_id = callback.from_user.id
    athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    if is_female:
        prompt_weight_text = (
            "⚖️ <b>የዚህ ሳምንት እሁድ Check-in</b>\n\n"
            "ጠዋት በባዶ ሆድ የተመዘንሽውን ክብደት በቁጥር ላኪልኝ (ለምሳሌ 61.5):"
        )
    else:
        prompt_weight_text = (
            "⚖️ <b>የዚህ ሳምንት እሁድ Check-in</b>\n\n"
            "ጠዋት በባዶ ሆድ የተመዘንከውን ክብደት በቁጥር ላክልኝ (ለምሳሌ 68.5):"
        )
    await state.set_state(CheckinFSM.weight)
    await callback.message.answer(prompt_weight_text, parse_mode="HTML")


@router.message(CheckinFSM.weight)
async def handle_checkin_weight(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text, bot)
        return

    user_id = message.from_user.id
    athlete = await db.get_athlete(user_id)
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")

    w_val = extract_weight(text)
    if not w_val:
        err = (
            "ክብደትሽን በቁጥር ብቻ ላኪ (ለምሳሌ 62 ወይም 64.5) 👇"
            if is_female else
            "ክብደትህን በቁጥር ብቻ ላክ (ለምሳሌ 68 ወይም 70.5) 👇"
        )
        await message.answer(err)
        return

    prompt_days = (
        f"ክብደት <b>{w_val} kg</b> ተመዝግቧል።\n\nበዚህ ሳምንት ስንት ቀን ጂም ገብተሽ ሰራሽ? 🏋️‍♀️"
        if is_female else
        f"ክብደት <b>{w_val} kg</b> ተመዝግቧል።\n\nበዚህ ሳምንት ስንት ቀን ጂም ገብተህ ሰራህ? 🏋️"
    )
    await asyncio.gather(
        state.update_data(current_weight=w_val),
        state.set_state(CheckinFSM.workouts),
    )
    await message.answer(prompt_days, parse_mode="HTML", reply_markup=get_checkin_workouts_keyboard())


@router.callback_query(CheckinFSM.workouts, F.data.startswith("chk_days:"))
async def handle_checkin_days(callback: CallbackQuery, state: FSMContext):
    asyncio.create_task(safe_answer(callback, "Check-in ተመዝግቧል!"))
    asyncio.create_task(safe_delete(callback.message))

    workouts = int(callback.data.split(":")[1])
    data = await state.get_data()
    weight = data.get("current_weight", 60.0)
    user_id = callback.from_user.id

    athlete, last_checkin, _ = await asyncio.gather(
        db.get_athlete(user_id),
        db.get_latest_checkin(user_id),
        state.clear(),
    )
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")
    start_w = float((athlete or {}).get("weight_kg") or weight)
    next_week = (last_checkin["week_number"] + 1) if last_checkin else 1

    await db.record_checkin(
        athlete_id=user_id,
        week_number=next_week,
        weight_kg=weight,
        workouts_completed=workouts,
    )

    delta = round(weight - start_w, 1)
    delta_str = f"{'+' if delta > 0 else ''}{delta} kg ከመነሻ"

    if is_female:
        congrats_text = (
            f"🎉 <b>የሳምንት {next_week} Check-in ተመዝግቧል!</b>\n\n"
            f"• ክብደት: <b>{weight} kg</b> ({delta_str})\n"
            f"• የሰራሽው ቀናት: <b>{workouts} ቀን</b>\n\n"
            "ወጥ ሆነሽ ቀጥይ፣ ሚዛን ላይ ብቻ አትቸኩዪ፣ በልብስሽና በመስታወት የሚታየውን ለውጥም ተከታተዪ 💪✨"
        )
    else:
        congrats_text = (
            f"🎉 <b>የሳምንት {next_week} Check-in ተመዝግቧል!</b>\n\n"
            f"• ክብደት: <b>{weight} kg</b> ({delta_str})\n"
            f"• የሰራኸው ቀናት: <b>{workouts} ቀን</b>\n\n"
            "ወጥ ሆነህ ቀጥል፣ ሚዛን ላይ ብቻ አትጨነቅ፣ በልብስህና በመስታወት የሚታየውን ለውጥም ተከታተል 💪🔥"
        )
    await callback.message.answer(congrats_text, parse_mode="HTML", reply_markup=get_user_main_menu())


@router.callback_query(F.data == "checkin:history")
async def handle_checkin_history(callback: CallbackQuery):
    asyncio.create_task(safe_answer(callback))
    user_id = callback.from_user.id

    athlete, checkins = await asyncio.gather(
        db.get_athlete(user_id),
        db.get_athlete_checkins(user_id),
    )
    is_female = bool(athlete and athlete.get("gender") == "FEMALE")
    start_w = float((athlete or {}).get("weight_kg") or 60.0)

    if not checkins:
        empty_msg = (
            "📜 ገና የተመዘገበ Check-in የለሽም። የመጀመሪያውን ሳምንት ስትጨርሺ እዚህ መዝግቢ 👇"
            if is_female else
            "📜 ገና የተመዘገበ Check-in የለህም። የመጀመሪያውን ሳምንት ስትጨርስ እዚህ መዝግብ 👇"
        )
        await callback.message.answer(
            empty_msg,
            parse_mode="HTML",
            reply_markup=get_athlete_plan_keyboard(has_active_order=True),
        )
        return

    lines = [
        "📊 <b>የኔ Record እና ሳምንታዊ ውጤቶች</b>\n",
        f"• መነሻ ክብደት (Day 1): <code>{start_w:.1f} kg</code>",
    ]
    for c in checkins:
        w_val = float(c["weight_kg"])
        d = round(w_val - start_w, 1)
        sign = "+" if d > 0 else ""
        lines.append(
            f"• <b>Week {c['week_number']}:</b> <code>{w_val:.1f} kg</code> ({sign}{d:.1f} kg) "
            f"| {c['workouts_completed']} ቀን ✅"
        )

    lines.append(
        "\n💡 <i>አስታውሺ፣ በመስታወት እና በልብስ የሚታየው ለውጥ ከሚዛን ቁጥር ይቀድማል!</i>"
        if is_female else
        "\n💡 <i>አስታውስ፣ በመስታወት እና በልብስ የሚታየው ለውጥ ከሚዛን ቁጥር ይቀድማል!</i>"
    )
    await callback.message.answer("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------
# Free-Text Inquiry Forwarder -> Admin DM + Support Bot Redirect
# ---------------------------------------------------------
async def _forward_inquiry_to_admins(
    bot: Bot,
    user_id: int,
    full_name: str,
    username: Optional[str],
    athlete: Optional[dict],
    raw_text: str,
):
    if not settings.admin_ids_list:
        return

    safe_name = html.escape(full_name or "Member")
    safe_uname = f"@{html.escape(username)}" if username else "No Username"
    state_code = html.escape(str((athlete or {}).get("onboarding_state") or "NEW"))
    goal_val = html.escape(str((athlete or {}).get("primary_goal") or "Not Set"))
    weight_val = html.escape(str((athlete or {}).get("weight_kg") or "N/A"))
    safe_query = html.escape(raw_text[:1000] if raw_text else "[Non-text message]")

    admin_card = (
        "💬 <b>NEW USER MESSAGE // INQUIRY</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {safe_name} ({safe_uname})\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📍 <b>State:</b> <code>{state_code}</code> | 🎯 <code>{goal_val}</code> | ⚖️ <code>{weight_val} kg</code>\n\n"
        f"📩 <b>Message:</b>\n<i>\"{safe_query}\"</i>\n\n"
        "💡 <i>Swipe/Reply directly to this message or tap Quick Reply below.</i>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Quick Reply", callback_data=f"adm_reply:{user_id}")
    if username:
        kb.button(text="💬 Open User Chat", url=f"https://t.me/{username}")
    else:
        kb.button(text="💬 Open User Chat", url=f"tg://user?id={user_id}")
    kb.adjust(1, 1)
    markup = kb.as_markup()

    for admin_id in settings.admin_ids_list:
        try:
            await bot.send_message(chat_id=admin_id, text=admin_card, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            logger.warning(f"Failed forwarding inquiry to admin {admin_id}: {e}")


@router.message()
async def handle_fallback_message(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    user_id = message.from_user.id
    full_name = message.from_user.full_name or "አባል"
    username = message.from_user.username

    athlete = await db.get_athlete(user_id)
    if not athlete:
        athlete = await db.upsert_athlete(user_id, full_name, username)

    state_code = athlete.get("onboarding_state", "START")
    is_female = athlete.get("gender") == "FEMALE"
    has_gender = athlete.get("gender") in ("FEMALE", "MALE")

    # Seamless recovery if server restarted while waiting for typed Age or Weight
    if state_code == "GENDER_SET":
        age_val = extract_age(text)
        if age_val:
            updated = await db.update_athlete_fields(
                user_id,
                age=age_val,
                age_range=str(age_val),
                onboarding_state="AGE_SET",
            )
            await prompt_weight(message.chat.id, user_id, bot, state, athlete=updated)
            return

    if state_code == "AGE_SET":
        weight_val = extract_weight(text)
        if weight_val:
            updated = await db.update_athlete_fields(user_id, weight_kg=weight_val, onboarding_state="WEIGHT_SET")
            await prompt_goal(message.chat.id, user_id, bot, athlete=updated)
            return

    # Forward message to admin in background (zero latency impact on user reply)
    asyncio.create_task(
        _forward_inquiry_to_admins(
            bot=bot,
            user_id=user_id,
            full_name=full_name,
            username=username,
            athlete=athlete,
            raw_text=text or message.caption or "[Media/Sticker]",
        )
    )

    support_ref = f"@{html.escape(settings.SUPPORT_BOT_USERNAME)}"
    if has_gender and is_female:
        reply_text = (
            "መልዕክትሽን ወደ አሰልጣኝ ብሩክታዊት ልኬዋለሁ! 📩\n\n"
            f"ቀጥታ እና ፈጣን ምላሽ ከፈለግሽ Support ቦታችን ላይ አናግሪን 👉 {support_ref}\n\n"
            "<i>(ወይም ፕላንሽን ለማስጀመር /start የሚለውን ንኪ)</i>"
        )
    elif has_gender:
        reply_text = (
            "መልዕክትህን ወደ አሰልጣኝ ብሩክታዊት ልኬዋለሁ! 📩\n\n"
            f"ቀጥታ እና ፈጣን ምላሽ ከፈለግህ Support ቦታችን ላይ አናግረን 👉 {support_ref}\n\n"
            "<i>(ወይም ፕላንህን ለማስጀመር /start የሚለውን ንካ)</i>"
        )
    else:
        reply_text = (
            "መልዕክትዎን ወደ አሰልጣኝ ብሩክታዊት ልኬዋለሁ! 📩\n\n"
            f"ቀጥታ እና ፈጣን እርዳታ ከፈለጉ Support ቦታችንን ያናግሩ 👉 {support_ref}\n\n"
            "<i>(ለመጀመር /start የሚለውን ይንኩ)</i>"
        )

    await message.answer(reply_text, parse_mode="HTML", reply_markup=get_support_keyboard())
