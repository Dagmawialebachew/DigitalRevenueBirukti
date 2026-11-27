import html
from typing import Dict, Any
from utils.tg_helpers import format_age_display


def _round_50(value: float) -> int:
    return int(round(value / 50.0) * 50)


def _round_5(value: float) -> int:
    return int(round(value / 5.0) * 5)


def generate_athlete_diagnostic_card(athlete: Dict[str, Any], user_id: int) -> str:
    """
    Generates a grounded Member Profile Card with Amharic goal/focus labels
    matching the inline button selections and range-only calorie/protein targets.
    """
    full_name = html.escape(athlete.get("full_name") or "አባል")
    gender = athlete.get("gender", "FEMALE")
    weight = float(athlete.get("weight_kg") or 60.0)
    goal = athlete.get("primary_goal", "BOOTY_CURVES")
    days = athlete.get("days_per_week") or 4

    client_code = f"BF-{user_id % 10000:04d}"
    gender_icon = "👩 ሴት" if gender == "FEMALE" else "👨 ወንድ"
    age_display = html.escape(format_age_display(athlete))

    maint = weight * 32.0
    if goal == "FAT_LOSS":
        center_kcal = max(1350.0, maint - 400.0)
        kcal_min = _round_50(center_kcal - 100.0)
        kcal_max = _round_50(center_kcal + 100.0)
    else:
        center_kcal = maint + 275.0
        kcal_min = _round_50(center_kcal - 100.0)
        kcal_max = _round_50(center_kcal + 100.0)

    prot_min = max(60, _round_5(weight * 1.6))
    prot_max = max(prot_min + 15, _round_5(weight * 2.0))

    water_range = "2.5 - 3.0L" if weight < 65 else "3.0 - 4.0L"

    if gender == "FEMALE":
        if goal == "FAT_LOSS":
            goal_title = "🔥 ቦርጭና ስብ መቀነስ"
            focus_note = "ቦርጭ እና የስብ መጠን መቀነስ"
        elif goal == "MUSCLE_GAIN":
            goal_title = "✨ ሙሉ ሰውነት ማሳመር"
            focus_note = "ሙሉ ሰውነትን ማጠንከርና ቅርጽ ማሳመር"
        else:
            goal_title = "🍑 ዳሌና መቀመጫ ማውጣት"
            focus_note = "ዳሌና መቀመጫ ማሳደግ፣ ወገብ ማጥበብ"
    else:
        if goal == "FAT_LOSS":
            goal_title = "🔥 ቦርጭና ስብ መቀነስ"
            focus_note = "ቦርጭ እና የስብ መጠን መቀነስ"
        else:
            goal_title = "💪 ጡንቻ ግንባታ"
            focus_note = "ደረት፣ ጀርባና ትከሻን በትክክለኛ ፎርም መገንባት"

    card = (
        "🎫 <b>የአባልነት መታወቂያ // MEMBER PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 <b>ስም:</b> {full_name}\n"
        f"🆔 <b>መለያ ቁጥር:</b> {client_code}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🧬 <b>ፕላን:</b> {gender_icon} | በሳምንት {days} ቀን\n"
        f"🎂 <b>ዕድሜ:</b> {age_display}\n"
        f"🎯 <b>ዋና ግብ:</b> {html.escape(goal_title)}\n"
        f"🔥 <b>የቀን ካሎሪ ክልል:</b> {kcal_min:,} - {kcal_max:,} kcal\n"
        f"🥩 <b>የቀን ፕሮቲን ክልል:</b> {prot_min} - {prot_max}g\n"
        f"💧 <b>የቀን ውሃ:</b> {water_range}\n"
        f"📌 <b>ዋና ትኩረት:</b> {html.escape(focus_note)}\n"
        "🔒 <b>ሁኔታ:</b> ፕላኑ ገና አልተከፈተም (LOCKED)\n"
        "━━━━━━━━━━━━━━━━"
    )
    return card
