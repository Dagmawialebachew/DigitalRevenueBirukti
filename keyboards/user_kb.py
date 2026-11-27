from aiogram.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import settings


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
        input_field_placeholder="አማራጭ..."
    )


# -------------------------------------------------------------
# Support Redirect Keyboard
# -------------------------------------------------------------
def get_support_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💬 Support አናግር (@{settings.SUPPORT_BOT_USERNAME})",
        url=f"https://t.me/{settings.SUPPORT_BOT_USERNAME}",
    )
    builder.adjust(1)
    return builder.as_markup()


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
    builder.button(text="18 - 24", callback_data="age:18-24")
    builder.button(text="25 - 34", callback_data="age:25-34")
    builder.button(text="35 - 44", callback_data="age:35-44")
    builder.button(text="45+", callback_data="age:45+")
    builder.adjust(2, 2)
    return builder.as_markup()


def get_weight_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="< 55 kg", callback_data="weight:52")
    builder.button(text="55 - 65 kg", callback_data="weight:60")
    builder.button(text="66 - 75 kg", callback_data="weight:70")
    builder.button(text="76 - 85 kg", callback_data="weight:80")
    builder.button(text="> 85 kg", callback_data="weight:90")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_goal_keyboard(is_female: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_female:
        builder.button(text="🍑 Booty & Curves (ዳሌና መቀመጫ ማውጣት)", callback_data="goal:BOOTY_CURVES")
        builder.button(text="🔥 Fat Loss (ቦርጭና ስብ መቀነስ)", callback_data="goal:FAT_LOSS")
        builder.button(text="✨ Muscle & Tone (ሙሉ ሰውነት ማሳመር)", callback_data="goal:MUSCLE_GAIN")
    else:
        builder.button(text="💪 Muscle Gain (ጡንቻ ግንባታ)", callback_data="goal:MUSCLE_GAIN")
        builder.button(text="🔥 Belly Fat Shred (ቦርጭና ስብ መቀነስ)", callback_data="goal:FAT_LOSS")
    builder.adjust(1)
    return builder.as_markup()


def get_frequency_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏋️‍♀️ 3 ቀን በሳምንት", callback_data="freq:3")
    builder.button(text="🏋️‍♀️ 4 ቀን በሳምንት", callback_data="freq:4")
    builder.adjust(2)
    return builder.as_markup()


def get_level_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌱 ጀማሪ (Beginner)", callback_data="level:BEGINNER")
    builder.button(text="⚡ መካከለኛ (Intermediate)", callback_data="level:INTERMEDIATE")
    builder.adjust(2)
    return builder.as_markup()


def get_commitment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="ቃል እገባለሁ፣ አብረን እንጀምር 🔥", callback_data="commit_YES")
    builder.adjust(1)
    return builder.as_markup()


# -------------------------------------------------------------
# Offer Pitch CTA & Clean Payment Page Keyboards
# -------------------------------------------------------------
def get_offer_cta_keyboard(price_etb: int) -> InlineKeyboardMarkup:
    """Single green CTA button on Stage 1 psychological pitch page."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"💳 ክፍያ ፈጽም ({price_etb} ብር)", callback_data="open_payment_page", style="success")
    builder.adjust(1)
    return builder.as_markup()


def get_payment_action_keyboard(cbe_acc: str, boa_acc: str) -> InlineKeyboardMarkup:
    """Dedicated Stage 2 payment page copy buttons (CBE & BOA only)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏦 CBE ቁጥር ኮፒ", copy_text={"text": cbe_acc})
    builder.button(text="🏦 BOA ቁጥር ኮፒ", copy_text={"text": boa_acc})
    builder.adjust(2)
    return builder.as_markup()


# -------------------------------------------------------------
# Member Transformation & Check-in Keyboards
# -------------------------------------------------------------
def get_athlete_plan_keyboard(has_active_order: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_active_order:
        builder.button(text="📝 ሳምንታዊ Check-in", callback_data="checkin:new", style="success")
        builder.button(text="📊 የኔ Record", callback_data="checkin:history")
        builder.adjust(2)
    else:
        builder.button(text="🔥 8-ሳምንቱን ልጀምር", callback_data="buy_now", style="success")
        builder.adjust(1)
    return builder.as_markup()


def get_checkin_workouts_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="2 ቀን", callback_data="chk_days:2")
    builder.button(text="3 ቀን", callback_data="chk_days:3")
    builder.button(text="4 ቀን", callback_data="chk_days:4")
    builder.button(text="5+ ቀን", callback_data="chk_days:5")
    builder.adjust(2, 2)
    return builder.as_markup()


# -------------------------------------------------------------
# Smart State Resumption Keyboards
# -------------------------------------------------------------
def get_resume_keyboard(step: str, cbe_acc: str, boa_acc: str, is_female: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    restart_label = "🔄 እንደገና ከመጀመሪያ ጀምሪ" if is_female else "🔄 እንደገና ከመጀመሪያ ጀምር"
    if step == "CHECKOUT_PITCHED":
        builder.button(text="🏦 CBE ቁጥር ኮፒ", copy_text={"text": cbe_acc})
        builder.button(text="🏦 BOA ቁጥር ኮፒ", copy_text={"text": boa_acc})
        builder.button(text=restart_label, callback_data="restart_flow")
        builder.adjust(2, 1)
    else:
        builder.button(text="➡️ የቀረኝን ጥያቄ ልመልስ", callback_data="resume_onboarding")
        builder.button(text=restart_label, callback_data="restart_flow")
        builder.adjust(1, 1)
    return builder.as_markup()
