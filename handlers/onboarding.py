import asyncio
import os
import re
import uuid
import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.enums import ChatAction

from database.db import db
from config import settings
from keyboards.user_kb import (
    get_user_main_menu,
    get_gender_keyboard,
    get_age_keyboard,
    get_weight_keyboard,
    get_goal_keyboard,
    get_frequency_keyboard,
    get_level_keyboard,
    get_payment_action_keyboard,
    get_athlete_plan_keyboard,
    get_checkin_workouts_keyboard,
    get_resume_keyboard
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
    "ℹ️ ስለ ብሩክቲ", "ℹ️ ስለ ብሩክታዊት (@gibdaw)"
}

# ---------------------------------------------------------
# Helper: Parse Numbers Safely
# ---------------------------------------------------------
def extract_age(text: str) -> int | None:
    match = re.search(r'\b(1[4-9]|[2-8][0-9]|90)\b', text)
    if match:
        return int(match.group(1))
    return None

def extract_weight(text: str) -> float | None:
    match = re.search(r'\b([3-9][0-9]|1[0-9]{2}|200)(?:\.([0-9]+))?\b', text)
    if match:
        return float(match.group(0))
    return None


# ---------------------------------------------------------
# Step 1: /start -> Smart Welcome / State Resumption
# ---------------------------------------------------------
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    full_name = user.full_name or "አትሌት"
    username = user.username

    # Fetch existing athlete state before upsert
    existing_athlete = await db.get_athlete(user.id)
    athlete = await db.upsert_athlete(user.id, full_name, username)

    reply_kb = get_user_main_menu()
    await message.answer("ሰላም! ከታች ያለውን ሜኑ በመጠቀም በማንኛውም ጊዜ መረጃዎችን ማግኘት ይችላሉ።", reply_markup=reply_kb)

    if existing_athlete:
        is_fem = existing_athlete.get("gender") == "FEMALE"
        state_code = existing_athlete.get("onboarding_state", "START")

        # 1. Active Paid Member
        async with db.pool.acquire() as conn:
            verified_order = await conn.fetchrow(
                "SELECT * FROM orders WHERE athlete_id = $1 AND status IN ('VERIFIED', 'DELIVERED') ORDER BY created_at DESC LIMIT 1;",
                user.id
            )

        if verified_order:
            if is_fem:
                welcome_back = (
                    "ሰላም ቆንጆዬ! 👋 እንኳን ተመልሰሽ መጣሽ!\n\n"
                    f"የ 8-ሳምንቱ የ **{verified_order['sku']}** ፕላንሽ ንቁ ነው። "
                    "ከታች ባለው ሜኑ **'🏋️‍♀️ የኔ ፕላን'** የሚለውን በመጫን የዚህን ሳምንት ውጤትሽንና Check-in መመዝገብ ትችያለሽ! 🔥"
                )
            else:
                welcome_back = (
                    "ሰላም ወንድሜ! 👋 እንኳን ተመልሰህ መጣህ!\n\n"
                    f"የ 8-ሳምንቱ የ **{verified_order['sku']}** ፕላንህ ንቁ ነው። "
                    "ከታች ባለው ሜኑ **'🏋️‍♀️ የኔ ፕላን'** የሚለውን በመጫን የዚህን ሳምንት ውጤትህንና Check-in መመዝገብ ትችላለህ! 💪"
                )
            await message.answer(welcome_back, parse_mode="Markdown", reply_markup=get_athlete_plan_keyboard(has_active_order=True))
            return

        # 2. Receipt Submitted (Pending Admin Review)
        pending_order = await db.get_latest_pending_order(user.id)
        if pending_order and pending_order.get("receipt_file_id"):
            wait_text = (
                "ሰላም ቆንጆዬ! 👋 የላክሽው የክፍያ ደረሰኝ በግምገማ ላይ ነው። "
                "በጥቂት ደቂቃዎች ውስጥ አረጋግጠን የሙሉ 8-ሳምንት ፕላንሽን PDF እንልክልሻለን ⏳"
                if is_fem else
                "ሰላም ወንድሜ! 👋 የላክኸው የክፍያ ደረሰኝ በግምገማ ላይ ነው። "
                "በጥቂት ደቂቃዎች ውስጥ አረጋግጠን የሙሉ 8-ሳምንት ፕላንህን PDF እንልክልሃለን ⏳"
            )
            await message.answer(wait_text, parse_mode="Markdown")
            return

        # 3. Reached Checkout (Viewed Bank Accounts)
        if state_code == "CHECKOUT_PITCHED":
            resume_text = (
                "ሰላም ቆንጆዬ! 👋 እንኳን ተመልሰሽ መጣሽ!\n\n"
                "ላንቺ ያዘጋጀሁልሽ የ 8-ሳምንቱ የትሬኒንግ ፕላን ዝግጁ ነው። ክፍያውን እንደፈጸምሽ ደረሰኝሽን እዚህ ላኪልኝ 👇"
                if is_fem else
                "ሰላም ወንድሜ! 👋 እንኳን ተመልሰህ መጣህ!\n\n"
                "ላንተ ያዘጋጀሁልህ የ 8-ሳምንቱ የትሬኒንግ ፕላን ዝግጁ ነው። ክፍያውን እንደፈጸምክ ደረሰኝህን እዚህ ላክልኝ 👇"
            )
            resume_kb = get_resume_keyboard("CHECKOUT_PITCHED", settings.CBE_ACCOUNT, settings.TELEBIRR_ACCOUNT)
            await message.answer(resume_text, parse_mode="Markdown", reply_markup=resume_kb)
            return

        # 4. Incomplete Onboarding (Paused Midway)
        if state_code in ("GENDER_SET", "AGE_SET", "WEIGHT_SET", "GOAL_SET", "SPLIT_SET", "DIAGNOSTIC_READY"):
            resume_text = (
                "ሰላም ቆንጆዬ! 👋 እንኳን ተመልሰሽ መጣሽ!\n\n"
                "ባለፈው የጀመርነውን የፕላን ዝግጅት እንጨርስ? ከታች **'➡️ የቀረኝን ጥያቄ ልመልስ'** የሚለውን ንኪው 👇"
                if is_fem else
                "ሰላም ወንድሜ! 👋 እንኳን ተመልሰህ መጣህ!\n\n"
                "ባለፈው የጀመርነውን የፕላን ዝግጅት እንጨርስ? ከታች **'➡️ የቀረኝን ጥያቄ ልመልስ'** የሚለውን ንካው 👇"
            )
            resume_kb = get_resume_keyboard("ONBOARDING", settings.CBE_ACCOUNT, settings.TELEBIRR_ACCOUNT)
            await message.answer(resume_text, parse_mode="Markdown", reply_markup=resume_kb)
            return

    # 5. Brand New Visitor
    caption = (
        "ሰላም! እንኳን ደህና መጡ! 👋\n\n"
        "እኔ **ብሩክታዊት (@gibdaw)** እባላለሁ። ወደ እኔ ኦፊሴላዊ የቴሌግራም ቦት እንኳን በደህና መጡ! ✨\n\n"
        "እዚህ ጋር የእርስዎን ግብ፣ እድሜና አሁን ያሉበትን ቁመና መሰረት ያደረገ ትክክለኛ የ 8-ሳምንት "
        "የጂም እና የቤት ውስጥ Workout ፕሮግራም ያገኛሉ።\n\n"
        "የእርስዎን ምርጥ የሰውነት ቅርጽ አብረን ለመስራት ጥቂት ጥያቄዎችን እንመልስ።\n\n"
        "መጀመሪያ ጾታዎን ይምረጡ 👇"
    )

    welcome_photo_path = os.path.join(settings.resolved_image_dir, "welcome_biruktawit.jpg")
    gender_kb = get_gender_keyboard()

    if os.path.exists(welcome_photo_path):
        photo = FSInputFile(welcome_photo_path)
        await bot.send_photo(message.chat.id, photo=photo, caption=caption, parse_mode="Markdown", reply_markup=gender_kb)
    else:
        await message.answer(caption, parse_mode="Markdown", reply_markup=gender_kb)


# ---------------------------------------------------------
# State Resumption & Restart Callbacks
# ---------------------------------------------------------
@router.callback_query(F.data == "restart_flow")
async def handle_restart_flow(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = callback.from_user.id
    await db.reset_athlete_onboarding(user_id)
    await callback.answer("ከመጀመሪያ ተጀምሯል!")

    caption = (
        "ሰላም እንደገና! 👋 አብረን ከዜሮ እንጀምር።\n\n"
        "የእርስዎን ትክክለኛ የ 8-ሳምንት ፕሮግራም ለመወሰን መጀመሪያ ጾታዎን ይምረጡ 👇"
    )
    gender_kb = get_gender_keyboard()
    await callback.message.answer(caption, parse_mode="Markdown", reply_markup=gender_kb)


@router.callback_query(F.data == "resume_onboarding")
async def handle_resume_onboarding(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    athlete = await db.get_athlete(user_id)
    await callback.answer()

    if not athlete:
        await callback.message.answer("መጀመሪያ ጾታዎን ይምረጡ 👇", reply_markup=get_gender_keyboard())
        return

    state_code = athlete.get("onboarding_state", "START")

    if state_code == "GENDER_SET":
        await callback.message.answer("በጣም ጥሩ! እድሜዎ ስንት ነው? 🎯", reply_markup=get_age_keyboard())
        await state.set_state(IntakeFSM.age)
    elif state_code == "AGE_SET":
        await prompt_weight(callback.message, state)
    elif state_code == "WEIGHT_SET":
        await prompt_goal(callback.message, user_id)
    elif state_code == "GOAL_SET":
        text = "በሳምንት ስንት ቀን ጂም ገብተው መስራት ይችላሉ? 🗓️"
        await callback.message.answer(text, reply_markup=get_frequency_keyboard())
    elif state_code == "SPLIT_SET":
        text = "በጂም ልምምድ ላይ ያለዎት ልምድ ምን ያህል ነው? 🏋️"
        await callback.message.answer(text, reply_markup=get_level_keyboard())
    elif state_code == "DIAGNOSTIC_READY":
        await handle_level_choice(callback, bot)
    else:
        await callback.message.answer("መጀመሪያ ጾታዎን ይምረጡ 👇", reply_markup=get_gender_keyboard())


# ---------------------------------------------------------
# Step 2: Gender Selection -> Ask Age
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("gender:"))
async def handle_gender_choice(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split(":")[1]
    await db.update_athlete_field(callback.from_user.id, "gender", gender)
    await db.update_athlete_field(callback.from_user.id, "onboarding_state", "GENDER_SET")
    await callback.answer()

    text = (
        "በጣም ጥሩ! እድሜዎ ስንት ነው? 🎯\n\n"
        "*(ከታች ካሉት ይምረጡ ወይም ቁጥሩን ጽፈው ይላኩት)*"
    )

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_age_keyboard())
    await state.set_state(IntakeFSM.age)


# ---------------------------------------------------------
# Step 3: Age (Callback or Direct Text Input) -> Ask Weight
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("age:"))
async def handle_age_callback(callback: CallbackQuery, state: FSMContext):
    age_val = int(callback.data.split(":")[1])
    await db.update_athlete_field(callback.from_user.id, "age", age_val)
    await db.update_athlete_field(callback.from_user.id, "onboarding_state", "AGE_SET")
    await callback.answer()
    await prompt_weight(callback.message, state)

@router.message(IntakeFSM.age)
async def handle_age_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    # Check if user tapped a persistent main menu button instead
    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text)
        return

    age_val = extract_age(text)
    if not age_val:
        await message.answer(
            "እባክዎ ትክክለኛ እድሜዎን በቁጥር ይላኩ (ለምሳሌ: 24 ወይም 28) 👇"
        )
        return

    await db.update_athlete_field(message.from_user.id, "age", age_val)
    await db.update_athlete_field(message.from_user.id, "onboarding_state", "AGE_SET")
    await prompt_weight(message, state)

async def prompt_weight(message: Message, state: FSMContext):
    text = (
        "አሁን ያለዎት የሰውነት ክብደት በኪሎግራም (kg) ስንት ነው? ⚖️\n\n"
        "*(ትክክለኛውን የካሎሪና የትሬኒንግ ጫና ለመወሰን ይጠቅመናል)*"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_weight_keyboard())
    await state.set_state(IntakeFSM.weight)


# ---------------------------------------------------------
# Step 4: Weight (Callback or Direct Text) -> Primary Goal
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("weight:"))
async def handle_weight_callback(callback: CallbackQuery, state: FSMContext):
    weight_val = float(callback.data.split(":")[1])
    await db.update_athlete_field(callback.from_user.id, "weight_kg", weight_val)
    await db.update_athlete_field(callback.from_user.id, "onboarding_state", "WEIGHT_SET")
    await callback.answer()
    await state.clear()
    await prompt_goal(callback.message, callback.from_user.id)

@router.message(IntakeFSM.weight)
async def handle_weight_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    # Check if user tapped a persistent main menu button instead
    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text)
        return

    weight_val = extract_weight(text)
    if not weight_val:
        await message.answer(
            "እባክዎ ትክክለኛ ክብደትዎን በኪሎግራም ይላኩ (ለምሳሌ: 62 ወይም 65.5 kg) 👇"
        )
        return

    await db.update_athlete_field(message.from_user.id, "weight_kg", weight_val)
    await db.update_athlete_field(message.from_user.id, "onboarding_state", "WEIGHT_SET")
    await state.clear()
    await prompt_goal(message, message.from_user.id)

async def prompt_goal(message: Message, user_id: int):
    athlete = await db.get_athlete(user_id)
    is_female = athlete and athlete.get("gender") == "FEMALE"

    text = "ዋናው ማሳካት የሚፈልጉት የሰውነት ግብ የትኛው ነው? 🔥"
    await message.answer(text, reply_markup=get_goal_keyboard(is_female))


# ---------------------------------------------------------
# Step 5: Primary Goal -> Weekly Frequency (3x vs 4x)
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("goal:"))
async def handle_goal_choice(callback: CallbackQuery):
    goal = callback.data.split(":")[1]
    await db.update_athlete_field(callback.from_user.id, "primary_goal", goal)
    await db.update_athlete_field(callback.from_user.id, "onboarding_state", "GOAL_SET")
    await callback.answer()

    text = "በሳምንት ስንት ቀን ጂም ገብተው መስራት ይችላሉ? 🗓️"
    await callback.message.edit_text(text, reply_markup=get_frequency_keyboard())


# ---------------------------------------------------------
# Step 6: Weekly Frequency -> Experience Level
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("freq:"))
async def handle_freq_choice(callback: CallbackQuery):
    days = int(callback.data.split(":")[1])
    await db.update_athlete_field(callback.from_user.id, "days_per_week", days)
    await db.update_athlete_field(callback.from_user.id, "onboarding_state", "SPLIT_SET")
    await callback.answer()

    text = "በጂም ልምምድ ላይ ያለዎት ልምድ ምን ያህል ነው? 🏋️"
    await callback.message.edit_text(text, reply_markup=get_level_keyboard())


# ---------------------------------------------------------
# Step 7: Diagnostic Card + FREE Value Drop + 8-Week Offer
# ---------------------------------------------------------
@router.callback_query(F.data.startswith("level:"))
async def handle_level_choice(callback: CallbackQuery, bot: Bot):
    level = callback.data.split(":")[1]
    user_id = callback.from_user.id
    await db.update_athlete_field(user_id, "experience_level", level)
    await db.update_athlete_field(user_id, "onboarding_state", "DIAGNOSTIC_READY")
    await callback.answer()

    athlete = await db.get_athlete(user_id)
    chat_id = callback.message.chat.id

    # 1. Dynamic Calibration Simulation (Perceived Coach Effort)
    is_fem = athlete.get("gender") == "FEMALE"
    g_slug = athlete.get("primary_goal", "BOOTY_CURVES")
    w_val = int(athlete.get("weight_kg", 60))
    d_val = athlete.get("days_per_week", 4)

    steps = [
        "🔍 መረጃሽን እየተመለከትኩ ነው..." if is_fem else "🔍 መረጃህን እየተመለከትኩ ነው...",
        f"🍑 ለ{w_val} kg ክብደትሽ ተስማሚ የሆነውን የ Booty ስፕሊት እያዘጋጀሁ ነው..." if (is_fem and g_slug == "BOOTY_CURVES") else (
            f"⚡ ለ{d_val} ቀናት የትሬኒንግ ስፕሊትሽን እያሰላሁ ነው..." if is_fem else f"⚡ ለ{d_val} ቀናት የትሬኒንግ ስፕሊትህን እያሰላሁ ነው..."
        ),
        "✨ ማጠቃለያሽ ተጠናቋል! ይሄው ተመልከቺው 👇" if is_fem else "✨ ማጠቃለያህ ተጠናቋል! ይሄው ተመልከተው 👇"
    ]
    for step in steps:
        try:
            await callback.message.edit_text(step)
            await asyncio.sleep(0.8)
        except Exception:
            pass

    from services.diagnostics import generate_athlete_diagnostic_card
    diagnostic_card = generate_athlete_diagnostic_card(athlete, user_id)
    await callback.message.answer(diagnostic_card, parse_mode="Markdown")

    # 2. Direct FREE Value Drop (No Commitment Button!)
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
    await asyncio.sleep(1.5)

    free_guide_path = os.path.join(settings.resolved_pdf_dir, "Biruktawit_Fitness_Foundation_Guide.pdf")
    if is_fem:
        free_msg = (
            "🎁 **ይሄ ላንቺ ያዘጋጀሁት የመጀመሪያው ነፃ ስጦታዬ ነው!**\n\n"
            "ቆንጆዬ፣ እኔ ራሴ ያዘጋጀሁትን 'የአካል ብቃትና ትክክለኛ ፎርም መመሪያ' (PDF) ከታች ልኬልሻለሁ። "
            "ጂም ውስጥ ስፖርት ስትሰሪ ሳትጎጂ ፈጣን ለውጥ እንድታዪ የሚረዱ ወሳኝ የፎርም ህጎች አሉት። አሁኑኑ አውርደሽ ተመልከቺው! 👇"
        )
    else:
        free_msg = (
            "🎁 **ይሄ ላንተ ያዘጋጀሁት የመጀመሪያው ነፃ ስጦታዬ ነው!**\n\n"
            "ወንድሜ፣ እኔ ራሴ ያዘጋጀሁትን 'የአካል ብቃትና ትክክለኛ ፎርም መመሪያ' (PDF) ከታች ልኬልሃለሁ። "
            "ጂም ውስጥ ስፖርት ስትሰራ ሳትጎዳ ፈጣን ለውጥ እንድታይ የሚረዱ ወሳኝ የፎርም ህጎች አሉት። አሁኑኑ አውርደህ ተመልከተው! 👇"
        )

    if os.path.exists(free_guide_path):
        doc = FSInputFile(free_guide_path)
        await bot.send_document(chat_id, document=doc, caption=free_msg, parse_mode="Markdown")
    else:
        await callback.message.answer(free_msg, parse_mode="Markdown")

    # 3. Create Pending Order & Pitch 8-Week Blueprint
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    gender = athlete.get("gender", "FEMALE")
    goal = athlete.get("primary_goal", "BOOTY_CURVES")
    days = athlete.get("days_per_week", 4)

    product = await db.get_catalog_product(gender, goal, days)
    sku = product["sku"] if product else f"BF-{gender[0]}-{days}X"

    await db.create_order(order_id, user_id, sku, settings.DEFAULT_PRICE_ETB)
    await db.update_athlete_field(user_id, "onboarding_state", "CHECKOUT_PITCHED")

    await asyncio.sleep(1.0)
    if is_fem:
        pitch_text = (
            "አሁን ደግሞ ይሄንን ላንቺ ያዘጋጀሁልሽን የተሟላ የ 8-ሳምንት የትራንስፎርሜሽን ፕሮግራም አብረን እንጀምር! 🔥\n\n"
            "📦 **በ 8-ሳምንቱ ፕሮግራምሽ ውስጥ ምን ምን ታገኛለሽ?**\n"
            "✅ ለእያንዳንዱ እንቅስቃሴ የቪዲዮ ማሳያ ሊንኮች (ትክክለኛ አሰራር)\n"
            "✅ በየሳምንቱ የሚጨምር ክብደትና የድግግሞሽ (Sets & Reps) ስሌት\n"
            "✅ የሰውነት ማሟሟቂያ (Warm-up) እና ማቀዝቀዣ (Cool-down)\n"
            "✅ የቤት ውስጥና የጂም አማራጮች\n\n"
            f"💰 **የሙሉ 8-ሳምንት ፕሮግራም ዋጋ:** `{settings.DEFAULT_PRICE_ETB} ብር` ብቻ\n\n"
            "**የመክፈያ የባንክ አካውንቶች:**\n"
            f"🏦 ንግድ ባንክ (CBE): `{settings.CBE_ACCOUNT}`\n"
            f"👤 ስም: **{settings.CBE_ACCOUNT_HOLDER}**\n\n"
            f"🏦 አቢሲኒያ ባንክ (BOA): `{settings.BOA_ACCOUNT}`\n"
            f"👤 ስም: **{settings.BOA_ACCOUNT_HOLDER}**\n\n"
            f"📱 ቴሌብር (Telebirr): `{settings.TELEBIRR_ACCOUNT}`\n"
            f"👤 ስም: **{settings.TELEBIRR_ACCOUNT_HOLDER}**\n\n"
            "⚠️ **ክፍያውን እንደፈጸምሽ የከፈልሽበትን ደረሰኝ ስክሪንሾት (Screenshot) እዚህ ላኪልኝ!** "
            "መረጃውን አረጋግጠን ወዲያውኑ የሙሉ ፕሮግራምሽን PDF እንልክልሻለን።"
        )
    else:
        pitch_text = (
            "አሁን ደግሞ ይሄንን ላንተ ያዘጋጀሁልህን የተሟላ የ 8-ሳምንት የትራንስፎርሜሽን ፕሮግራም አብረን እንጀምር! 🔥\n\n"
            "📦 **በ 8-ሳምንቱ ፕሮግራምህ ውስጥ ምን ምን ታገኛለህ?**\n"
            "✅ ለእያንዳንዱ እንቅስቃሴ የቪዲዮ ማሳያ ሊንኮች (ትክክለኛ አሰራር)\n"
            "✅ በየሳምንቱ የሚጨምር ክብደትና የድግግሞሽ (Sets & Reps) ስሌት\n"
            "✅ የሰውነት ማሟሟቂያ (Warm-up) እና ማቀዝቀዣ (Cool-down)\n"
            "✅ የቤት ውስጥና የጂም አማራጮች\n\n"
            f"💰 **የሙሉ 8-ሳምንት ፕሮግራም ዋጋ:** `{settings.DEFAULT_PRICE_ETB} ብር` ብቻ\n\n"
            "**የመክፈያ የባንክ አካውንቶች:**\n"
            f"🏦 ንግድ ባንክ (CBE): `{settings.CBE_ACCOUNT}`\n"
            f"👤 ስም: **{settings.CBE_ACCOUNT_HOLDER}**\n\n"
            f"🏦 አቢሲኒያ ባንክ (BOA): `{settings.BOA_ACCOUNT}`\n"
            f"👤 ስም: **{settings.BOA_ACCOUNT_HOLDER}**\n\n"
            f"📱 ቴሌብር (Telebirr): `{settings.TELEBIRR_ACCOUNT}`\n"
            f"👤 ስም: **{settings.TELEBIRR_ACCOUNT_HOLDER}**\n\n"
            "⚠️ **ክፍያውን እንደፈጸምክ የከፈልክበትን ደረሰኝ ስክሪንሾት (Screenshot) እዚህ ላክልኝ!** "
            "መረጃውን አረጋግጠን ወዲያውኑ የሙሉ ፕሮግራምህን PDF እንልክልሃለን።"
        )

    payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.TELEBIRR_ACCOUNT)
    await callback.message.answer(pitch_text, parse_mode="Markdown", reply_markup=payment_kb)


# ---------------------------------------------------------
# Dynamic Menu Routing (Avoids State Trapping)
# ---------------------------------------------------------
async def route_menu_action(message: Message, text: str):
    if text in ["🏋️‍♀️ የኔ ፕላን", "🏋️‍♀️ የእኔ ፕሮግራም"]:
        await handle_my_program_menu(message)
    elif text in ["💳 ክፍያ / ደረሰኝ", "💳 ክፍያ ፈጽም / ደረሰኝ ላክ"]:
        await handle_payment_menu(message)
    elif text in ["🎁 ነፃ መመሪያ", "🎁 ነፃ የፎርም መመሪያ (PDF)"]:
        await handle_free_guide_menu(message)
    elif text in ["ℹ️ ስለ ብሩክቲ", "ℹ️ ስለ ብሩክታዊት (@gibdaw)"]:
        await handle_about_menu(message)


# ---------------------------------------------------------
# User Main Menu Reply Handlers (100% Sheger Native Gym Voice)
# ---------------------------------------------------------
@router.message(F.text.in_({"🏋️‍♀️ የኔ ፕላን", "🏋️‍♀️ የእኔ ፕሮግራም"}))
async def handle_my_program_menu(message: Message):
    user_id = message.from_user.id
    athlete = await db.get_athlete(user_id)
    if not athlete:
        await message.answer("መጀመሪያ /start ብለው ፕሮፋይልዎን ያስተካክሉ።")
        return

    is_fem = athlete.get("gender") == "FEMALE"

    # Check verified orders
    async with db.pool.acquire() as conn:
        verified_order = await conn.fetchrow(
            "SELECT * FROM orders WHERE athlete_id = $1 AND status IN ('VERIFIED', 'DELIVERED') ORDER BY created_at DESC LIMIT 1;",
            user_id
        )

    if verified_order:
        sku = verified_order["sku"]
        checkins = await db.get_athlete_checkins(user_id)
        start_w = float(athlete.get("weight_kg") or 60.0)
        goal = athlete.get("primary_goal", "BOOTY_CURVES")

        if checkins:
            latest = checkins[-1]
            latest_w = float(latest["weight_kg"])
            diff = latest_w - start_w
            sign = "+" if diff > 0 else ""
            diff_str = f"{sign}{diff:.1f} kg"
            week_num = latest["week_number"]
            total_days = sum(c["workouts_completed"] for c in checkins)

            # Goal-specific encouraging feedback
            if goal in ("BOOTY_CURVES", "MUSCLE_GAIN"):
                coach_tip = "💡 *የ Booty & Muscle ምስጢር:* ሚዛን ላይ ቁጥሩ ባይቀንስም በስፖርቱ የሚመጣው የቅርጽ ለውጥ ነው ዋናው! 🔥"
            else:
                coach_tip = "💡 *የ Fat Loss ምስጢር:* ወጥነት (Consistency) ባገኘህ ቁጥር ስቡ እየቀለጠ ቅርጽህ ይወጣል! 🔥" if not is_fem else "💡 *የ Fat Loss ምስጢር:* ወጥነት (Consistency) ባገኘሽ ቁጥር ስቡ እየቀለጠ ቅርጽሽ ይወጣል! 🔥"

            if is_fem:
                progress_summary = (
                    f"📊 **የኔ Progress & Record:**\n"
                    f"• የመነሻ ክብደት (Day 1): `{start_w:.1f} kg`\n"
                    f"• የአሁኑ (Week {week_num}): `{latest_w:.1f} kg` ({diff_str})\n"
                    f"• ጂም የገባሽባቸው ቀናት: `{total_days} ቀናት`\n\n"
                    f"{coach_tip}\n\n"
                    f"የዚህን ሳምንት ውጤት ለመመዝገብ ከታች **'📝 ሳምንታዊ Check-in'** የሚለውን ንኪው!"
                )
            else:
                progress_summary = (
                    f"📊 **የኔ Progress & Record:**\n"
                    f"• የመነሻ ክብደት (Day 1): `{start_w:.1f} kg`\n"
                    f"• የአሁኑ (Week {week_num}): `{latest_w:.1f} kg` ({diff_str})\n"
                    f"• ጂም የገባህባቸው ቀናት: `{total_days} ቀናት`\n\n"
                    f"{coach_tip}\n\n"
                    f"የዚህን ሳምንት ውጤት ለመመዝገብ ከታች **'📝 ሳምንታዊ Check-in'** የሚለውን ንካው!"
                )
        else:
            if is_fem:
                progress_summary = (
                    f"🎯 **የመጀመሪያው ሳምንት Check-in አልተመዘገበም**\n"
                    f"• መነሻ ክብደትሽ: `{start_w:.1f} kg`\n\n"
                    f"የመጀመሪያውን ሳምንት ስፖርት ስትሰሪ ከታች **'📝 ሳምንታዊ Check-in'** በመጫን ክብደትሽንና የሰራሽባቸውን ቀናት እንመዝግብ!"
                )
            else:
                progress_summary = (
                    f"🎯 **የመጀመሪያው ሳምንት Check-in አልተመዘገበም**\n"
                    f"• መነሻ ክብደትህ: `{start_w:.1f} kg`\n\n"
                    f"የመጀመሪያውን ሳምንት ስፖርት ስትሰራ ከታች **'📝 ሳምንታዊ Check-in'** በመጫን ክብደትህንና የሰራህባቸውን ቀናት እንመዝግብ!"
                )

        header = (
            f"🎉 **ቆንጆዬ፣ የ 8-ሳምንቱ {sku} ፕላንሽ ንቁ ነው!** 🔥\n\n"
            if is_fem else
            f"🎉 **ወንድሜ፣ የ 8-ሳምንቱ {sku} ፕላንህ ንቁ ነው!** 🔥\n\n"
        )
        text = f"{header}{progress_summary}"
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_athlete_plan_keyboard(has_active_order=True)
        )
    else:
        if is_fem:
            text = (
                "📌 **ቆንጆዬ፣ ገና የ 8-ሳምንት ፕላንሽን አልጀመርሽም።**\n\n"
                "የ 8-ሳምንቱን የ Booty & Curves ወይም Fat Loss ፕላን ስትጀምሪ፣ "
                "በየሳምንቱ ክብደትሽን፣ ጂም የገባሽባቸውን ቀናትና ውጤትሽን እዚህ አብረን እንከታተላለን! 🔥\n\n"
                "ፕላኑን ጀምረን አብረን ውጤት እንድናመጣ ከታች **'🔥 8-ሳምንቱን ልጀምር'** የሚለውን ንኪው!"
            )
        else:
            text = (
                "📌 **ወንድሜ፣ ገና የ 8-ሳምንት ፕላንህን አልጀመርክም።**\n\n"
                "የ 8-ሳምንቱን የትሬኒንግ ፕላን ስትጀምር፣ "
                "በየሳምንቱ ክብደትህን፣ ጂም የገባህባቸውን ቀናትና ውጤትህን እዚህ አብረን እንከታተላለን! 💪\n\n"
                "ፕላኑን ጀምረን አብረን ውጤት እንድናመጣ ከታች **'🔥 8-ሳምንቱን ልጀምር'** የሚለውን ንካው!"
            )
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_athlete_plan_keyboard(has_active_order=False)
        )


@router.message(F.text.in_({"💳 ክፍያ / ደረሰኝ", "💳 ክፍያ ፈጽም / ደረሰኝ ላክ"}))
async def handle_payment_menu(message: Message):
    text = (
        "💳 **የክፍያ መመሪያና የባንክ አካውንቶች**\n\n"
        f"💰 **የሙሉ 8-ሳምንት ፕሮግራም ዋጋ:** `{settings.DEFAULT_PRICE_ETB} ብር`\n\n"
        f"🏦 ንግድ ባንክ (CBE): `{settings.CBE_ACCOUNT}`\n"
        f"👤 ስም: **{settings.CBE_ACCOUNT_HOLDER}**\n\n"
        f"🏦 አቢሲኒያ ባንክ (BOA): `{settings.BOA_ACCOUNT}`\n"
        f"👤 ስም: **{settings.BOA_ACCOUNT_HOLDER}**\n\n"
        f"📱 ቴሌብር (Telebirr): `{settings.TELEBIRR_ACCOUNT}`\n"
        f"👤 ስም: **{settings.TELEBIRR_ACCOUNT_HOLDER}**\n\n"
        "📸 **ክፍያውን እንደፈጸሙ የደረሰኙን ስክሪንሾት (Photo) በቀጥታ ወደዚህ ቻት ይላኩልን!**"
    )
    payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.TELEBIRR_ACCOUNT)
    await message.answer(text, parse_mode="Markdown", reply_markup=payment_kb)


@router.message(F.text.in_({"🎁 ነፃ መመሪያ", "🎁 ነፃ የፎርም መመሪያ (PDF)"}))
async def handle_free_guide_menu(message: Message, bot: Bot = None):
    chat_id = message.chat.id
    free_guide_path = os.path.join(settings.resolved_pdf_dir, "Biruktawit_Fitness_Foundation_Guide.pdf")
    free_msg = (
        "🎁 **የአካል ብቃትና ትክክለኛ ፎርም መመሪያ (PDF)**\n\n"
        "ይሄው ነፃ መመሪያዎን ከታች ልከንልዎታል። አውርደው ይመልከቱት! 👇"
    )
    if os.path.exists(free_guide_path) and bot:
        doc = FSInputFile(free_guide_path)
        await bot.send_document(chat_id, document=doc, caption=free_msg, parse_mode="Markdown")
    else:
        await message.answer(free_msg + "\n\n(ፋይሉ በቅርቡ ይጫናል። ጥያቄ ካለዎት በ @gibdaw ያግኙን።)")


@router.message(F.text.in_({"ℹ️ ስለ ብሩክቲ", "ℹ️ ስለ ብሩክታዊት (@gibdaw)"}))
async def handle_about_menu(message: Message):
    text = (
        "✨ **ስለ አሰልጣኝ ብሩክታዊት ፊክሬ (@gibdaw)**\n\n"
        "ብሩክታዊት ፊክሬ በአዲስ አበባ ውስጥ በሴቶችና በወንዶች የሰውነት ቅርጽ ማስተካከል፣ "
        "ዳሌና መቀመጫ ማውጣት (Booty & Hypertrophy) እንዲሁም ስብ ማቃጠል ላይ ያተኮረች "
        "የአካል ብቃት አሰልጣኝ ናት።\n\n"
        "🎯 **አላማችን:**\n"
        "በቀላሉ የሚተገበር፣ በሳይንሳዊ መንገድ የተረጋገጠ እና ዘላቂ ለውጥ የሚያመጣ የ 8-ሳምንት "
        "የአካል ብቃት ስልጠና መስጠት ነው።\n\n"
        "📲 **ኦፊሴላዊ የቴሌግራም አካውንት:** @gibdaw"
    )
    await message.answer(text, parse_mode="Markdown")


# ---------------------------------------------------------
# Athlete Check-in Flow & Deep Personalization (Native Slang)
# ---------------------------------------------------------
@router.callback_query(F.data == "checkin:new")
async def handle_checkin_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    athlete = await db.get_athlete(user_id)
    is_fem = athlete and athlete.get("gender") == "FEMALE"

    text = (
        "ሳምንታዊ Check-in 📝\n\n"
        f"ዛሬ ጠዋት በባዶ ሆድ ሚዛን ላይ ስትወ{'ጪ' if is_fem else 'ጣ'} ክብደት{'ሽ' if is_fem else 'ህ'} በኪሎግራም (kg) ስንት ነው? ⚖️\n\n"
        "*(ቁጥሩን ብቻ ጽፈው ይላኩ፣ ለምሳሌ: 61 ወይም 62.5)*"
    )
    await callback.message.answer(text)
    await state.set_state(CheckinFSM.weight)
    await callback.answer()


@router.message(CheckinFSM.weight)
async def handle_checkin_weight(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text in MENU_TEXTS:
        await state.clear()
        await route_menu_action(message, text)
        return

    weight_val = extract_weight(text)
    if not weight_val:
        await message.answer("እባክዎ ትክክለኛውን ክብደት በቁጥር ይላኩ (ለምሳሌ: 61.5) 👇")
        return

    await state.update_data(current_weight=weight_val)
    athlete = await db.get_athlete(message.from_user.id)
    is_fem = athlete and athlete.get("gender") == "FEMALE"

    prompt_days = (
        f"በጣም አሪፍ! `{weight_val} kg` ተመዝግቧል። 🎯\n\n"
        f"በዚህ ሳምንት ስንት ቀን ጂም ገብተ{'ሽ' if is_fem else 'ህ'} ሰራ{'ሽ' if is_fem else 'ህ'}? 🏋️"
    )
    await message.answer(prompt_days, parse_mode="Markdown", reply_markup=get_checkin_workouts_keyboard())
    await state.set_state(CheckinFSM.workouts)


@router.callback_query(F.data.startswith("chk_days:"))
async def handle_checkin_workouts(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.split(":")[1])
    data = await state.get_data()
    weight_val = data.get("current_weight", 60.0)
    user_id = callback.from_user.id

    athlete = await db.get_athlete(user_id)
    is_fem = athlete and athlete.get("gender") == "FEMALE"
    start_w = float(athlete.get("weight_kg") or weight_val)
    goal = athlete.get("primary_goal", "BOOTY_CURVES")

    # Determine week number from prior checkins
    existing_checkins = await db.get_athlete_checkins(user_id)
    week_num = min(len(existing_checkins) + 1, 8)

    # Record check-in to database
    await db.record_checkin(
        athlete_id=user_id,
        week_number=week_num,
        weight_kg=weight_val,
        workouts_completed=days
    )
    await state.clear()
    await callback.answer()

    diff = weight_val - start_w
    sign = "+" if diff > 0 else ""
    diff_str = f"{sign}{diff:.1f} kg"

    if goal in ("BOOTY_CURVES", "MUSCLE_GAIN"):
        encourage = (
            "በጣም ጎበዝ ቆንጆዬ! 🔥 ወጥነት (Consistency) ነው ትልቁ ሚስጥር። "
            "ሚዛን ላይ ያለው ብቻ ሳይሆን በስፖርቱ የሚመጣው የቅርጽ ለውጥ ነው የሚያምረው! "
            "በሚቀጥለው ሳምንት የበለጠ እንገፋበታለን በርቺ 💪✨"
            if is_fem else
            "አሪፍ ስራ ነው ወንድሜ! 💪 ወጥነት (Consistency) ነው ዋናው። "
            "በሚቀጥለው ሳምንት ደግሞ የበለጠ ክብደት እንገፋለን በርታ! 🔥"
        )
    else:
        encourage = (
            f"እሳት ነሽ ቆንጆዬ! 🔥 የደከምሽበት ውጤት እየታየ ነው። ይሄንኑ ወጥነት እንጠብቅ በርቺ 💪✨"
            if is_fem else
            f"አሪፍ ለውጥ ነው ወንድሜ! 💪 ይሄንኑ ወጥነት ጠብቀን እንቀጥላለን በርታ! 🔥"
        )

    congrats_text = (
        f"🎉 **የሳምንት {week_num} Check-in በተሳካ ሁኔታ ተመዝግቧል!**\n\n"
        f"⚖️ የአሁኑ ክብደት: `{weight_val} kg` ({diff_str} ከመነሻ)\n"
        f"🏋️ የተሰሩ ቀናት: `{days} ቀናት`\n\n"
        f"{encourage}"
    )
    await callback.message.answer(congrats_text, parse_mode="Markdown")


@router.callback_query(F.data == "checkin:history")
async def handle_checkin_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    checkins = await db.get_athlete_checkins(user_id)
    athlete = await db.get_athlete(user_id)
    start_w = float(athlete.get("weight_kg") or 60.0) if athlete else 60.0
    is_fem = athlete and athlete.get("gender") == "FEMALE"

    if not checkins:
        await callback.message.answer("📜 እስካሁን የተመዘገበ ሳምንታዊ Check-in የለም። የመጀመሪያውን ሳምንት ስፖርት ስትሰሩ ይመዝግቡ!")
        await callback.answer()
        return

    history_lines = [
        f"📊 **የኔ Record & ሳምንታዊ ውጤቶች**\n"
        f"• የመነሻ ክብደት (Day 1): `{start_w:.1f} kg`\n"
    ]
    for c in checkins:
        w_val = float(c["weight_kg"])
        d = w_val - start_w
        sign = "+" if d > 0 else ""
        history_lines.append(f"• **Week {c['week_number']}:** `{w_val:.1f} kg` ({sign}{d:.1f} kg) — {c['workouts_completed']} ቀናት ተሰርተዋል ✅")

    history_lines.append(f"\n💡 *ብሩክቲ:* ቀስ በቀስ የሚመጣ ለውጥ ነው ዘላቂው! በር{'ቺ' if is_fem else 'ታ'} 🔥")
    history_text = "\n".join(history_lines)
    await callback.message.answer(history_text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "buy_now")
async def handle_buy_now(callback: CallbackQuery):
    payment_kb = get_payment_action_keyboard(settings.CBE_ACCOUNT, settings.TELEBIRR_ACCOUNT)
    text = (
        "💳 **የክፍያ መመሪያና የባንክ አካውንቶች**\n\n"
        f"💰 **የሙሉ 8-ሳምንት ፕሮግራም ዋጋ:** `{settings.DEFAULT_PRICE_ETB} ብር` ብቻ\n\n"
        f"🏦 ንግድ ባንክ (CBE): `{settings.CBE_ACCOUNT}`\n"
        f"👤 ስም: **{settings.CBE_ACCOUNT_HOLDER}**\n\n"
        f"🏦 አቢሲኒያ ባንክ (BOA): `{settings.BOA_ACCOUNT}`\n"
        f"👤 ስም: **{settings.BOA_ACCOUNT_HOLDER}**\n\n"
        f"📱 ቴሌብር (Telebirr): `{settings.TELEBIRR_ACCOUNT}`\n"
        f"👤 ስም: **{settings.TELEBIRR_ACCOUNT_HOLDER}**\n\n"
        "📸 **ክፍያውን እንደፈጸሙ የደረሰኙን ስክሪንሾት (Photo) በቀጥታ ወደዚህ ቻት ይላኩልን!**"
    )
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=payment_kb)
    await callback.answer()


@router.callback_query(F.data == "send_receipt_guide")
async def handle_send_receipt_guide(callback: CallbackQuery):
    text = (
        "📸 **ደረሰኝ እንዴት እንደሚላክ:**\n\n"
        "ክፍያ በባንክ ወይም በቴሌብር እንደፈጸሙ፣ የደረሰኙን ስክሪንሾት (Screenshot) ወይም ፎቶ በቀጥታ ወደዚህ ቻት ይላኩልን!\n\n"
        "መረጃውን በ 1-3 ደቂቃ ውስጥ አረጋግጠን የሙሉ 8-ሳምንት ፕሮግራምዎን PDF እንልክልዎታለን።"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()
