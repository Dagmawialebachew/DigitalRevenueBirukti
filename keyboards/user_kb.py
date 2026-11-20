from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# -------------------------------------------------------------
# Main Menu Reply Keyboard (Short, Clean, Punchy Amharic)
# -------------------------------------------------------------
def get_user_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🏋️‍♀️ የኔ ፕላን")
    builder.button(text="💳 ክፍያ / ደረሰኝ")
    builder.button(text="🎁 ነፃ መመሪያ")
    builder.button(text="ℹ️ ስለ ብሩክቲ")
    builder.adjust(2, 2)
    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="አማራጭ ይምረጡ..."
    )

# -------------------------------------------------------------
# Onboarding Inline Keyboards (Compact Mobile-Friendly Buttons)
# -------------------------------------------------------------
def get_gender_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👩 ሴት", callback_data="gender:FEMALE")
    builder.button(text="👨 ወንድ", callback_data="gender:MALE")
    builder.adjust(2)
    return builder.as_markup()

def get_age_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="18-24", callback_data="age:21")
    builder.button(text="25-34", callback_data="age:28")
    builder.button(text="35-44", callback_data="age:38")
    builder.button(text="45+", callback_data="age:48")
    builder.adjust(2, 2)
    return builder.as_markup()

def get_weight_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="< 55 kg", callback_data="weight:52")
    builder.button(text="55-65 kg", callback_data="weight:60")
    builder.button(text="66-75 kg", callback_data="weight:70")
    builder.button(text="76-85 kg", callback_data="weight:80")
    builder.button(text="> 85 kg", callback_data="weight:90")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_goal_keyboard(is_female: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_female:
        builder.button(text="🍑 Booty & ዳሌ", callback_data="goal:BOOTY_CURVES")
        builder.button(text="🔥 Fat Loss", callback_data="goal:FAT_LOSS")
        builder.button(text="💪 Toning", callback_data="goal:MUSCLE_GAIN")
    else:
        builder.button(text="💪 Muscle Bulk", callback_data="goal:MUSCLE_GAIN")
        builder.button(text="🔥 Fat Loss", callback_data="goal:FAT_LOSS")
        builder.button(text="⚡ Strength", callback_data="goal:STRENGTH")
    builder.adjust(1)
    return builder.as_markup()

def get_frequency_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="3x / ሳምንት", callback_data="freq:3", style="primary")
    builder.button(text="4x / ሳምንት", callback_data="freq:4", style="primary")
    builder.adjust(2)
    return builder.as_markup()

def get_level_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌱 ጀማሪ", callback_data="level:BEGINNER")
    builder.button(text="⚡ መካከለኛ", callback_data="level:INTERMEDIATE")
    builder.adjust(2)
    return builder.as_markup()

# -------------------------------------------------------------
# Modern Checkout Keyboards (One-Tap Copy & Success Styling)
# -------------------------------------------------------------
def get_payment_action_keyboard(cbe_acc: str, telebirr_acc: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 CBE ኮፒ", copy_text={"text": cbe_acc})
    builder.button(text="📱 Telebirr ኮፒ", copy_text={"text": telebirr_acc})
    builder.button(text="📸 ደረሰኝ ላክ", callback_data="send_receipt_guide", style="success")
    builder.adjust(2, 1)
    return builder.as_markup()

# -------------------------------------------------------------
# Athlete Transformation & Check-in Keyboards (Native Sheger Slang)
# -------------------------------------------------------------
def get_athlete_plan_keyboard(has_active_order: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_active_order:
        builder.button(text="📝 ሳምንታዊ Check-in", callback_data="checkin:new", style="success")
        builder.button(text="📊 የኔ Record", callback_data="checkin:history", style="primary")
        builder.adjust(2)
    else:
        builder.button(text="🔥 8-ሳምንቱን ልጀምር", callback_data="buy_now", style="success")
        builder.adjust(1)
    return builder.as_markup()

def get_checkin_workouts_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="2 ቀናት", callback_data="chk_days:2")
    builder.button(text="3 ቀናት", callback_data="chk_days:3")
    builder.button(text="4 ቀናት", callback_data="chk_days:4")
    builder.button(text="5+ ቀናት", callback_data="chk_days:5")
    builder.adjust(2, 2)
    return builder.as_markup()

# -------------------------------------------------------------
# Smart State Resumption Keyboards
# -------------------------------------------------------------
def get_resume_keyboard(step: str, cbe_acc: str, telebirr_acc: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if step == "CHECKOUT_PITCHED":
        builder.button(text="📋 CBE ኮፒ", copy_text={"text": cbe_acc})
        builder.button(text="📱 Telebirr ኮፒ", copy_text={"text": telebirr_acc})
        builder.button(text="📸 ደረሰኝ ላክ", callback_data="send_receipt_guide", style="success")
        builder.button(text="🔄 እንደገና ከመጀመሪያ ጀምር", callback_data="restart_flow")
        builder.adjust(2, 1, 1)
    else:
        builder.button(text="➡️ የቀረኝን ጥያቄ ልመልስ", callback_data="resume_onboarding", style="success")
        builder.button(text="🔄 እንደገና ከመጀመሪያ ጀምር", callback_data="restart_flow")
        builder.adjust(1, 1)
    return builder.as_markup()
