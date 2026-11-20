from typing import Dict, Any

def generate_athlete_diagnostic_card(athlete: Dict[str, Any], user_id: int) -> str:
    """
    Generates a deeply personalized, authentic fitness diagnostic card
    free of pseudo-scientific Barnum statements or robotic jargon.
    """
    gender = athlete.get("gender", "FEMALE")
    age = athlete.get("age", 25)
    weight = float(athlete.get("weight_kg", 60.0))
    goal = athlete.get("primary_goal", "BOOTY_CURVES")
    days = athlete.get("days_per_week", 4)
    level = athlete.get("experience_level", "BEGINNER")

    client_code = f"BF-{user_id % 10000:04d}"
    gender_label = "ሴት" if gender == "FEMALE" else "ወንድ"
    level_label = "አዲስ ጀማሪ" if level == "BEGINNER" else "መካከለኛ ልምድ ያለው"

    # 1. Calculated Nutrition & Recovery Targets
    protein_mult = 1.8 if gender == "FEMALE" else 2.0
    daily_protein = int(weight * protein_mult)
    water_liters = round(weight * 0.04, 1)

    # 2. Split Recommendation
    if days == 3:
        split_desc = "3x በሳምንት // Full Body Hypertrophy Rotation"
    else:
        split_desc = "4x በሳምንት // Upper & Lower Specialized Split"

    # 3. Dynamic Coach Insights based on specific Goal & Profile
    if gender == "FEMALE":
        if goal == "BOOTY_CURVES":
            goal_title = "🍑 Booty & Curves (ዳሌና መቀመጫ ማውጣት)"
            focus_notes = (
                f"• ለእርስዎ {int(weight)} kg ክብደት በየቀኑ ~{daily_protein}g ፕሮቲን ያስፈልግዎታል።\n"
                "• በሳምንት 2 ሙሉ ቀናት በ Glutes (Hip Thrust, RDL, Split Squats) ላይ "
                "የ 3 ሰከንድ ቁጥጥር ያለው አወራረድ (Controlled Eccentrics) እንጠቀማለን።\n"
                "• ከልክ በላይ ረጅም ካርዲዮ መስራት ቅርጽን እንዳያጠፋ በሳምንት 20 ደቂቃ brisk walking ብቻ በቂ ነው።"
            )
        elif goal == "FAT_LOSS":
            goal_title = "🔥 Fat Loss & Toning (ስብ ማቃጠልና ቅርጽ መያዝ)"
            focus_notes = (
                f"• ለእርስዎ {int(weight)} kg ክብደት በቀን ~{daily_protein}g ፕሮቲን በመመገብ ሜታቦሊዝምዎ ሳይቀንስ ስብ እናቃጥላለን።\n"
                "• በድንገት ረሃብ ውስጥ ከመግባት ይልቅ በትንሽ የካሎሪ ቅነሳ (Moderate Deficit) ቅርጽዎን እንጠብቃለን።\n"
                "• የክብደት ልምምድ በማድረግ ሰውነትዎ ጠጣርና የታነጸ እንዲሆን ይደረጋል።"
            )
        else:
            goal_title = "💪 Muscle Shape & Core (ቅርጽና ጥንካሬ)"
            focus_notes = (
                f"• በቀን ~{daily_protein}g ፕሮቲን እና ቢያንስ {water_liters} ሊትር ንጹህ ውሃ መጠጣት ያስፈልጋል።\n"
                "• ደረት፣ ጀርባና የሆድ ጡንቻዎችን (Core) በእኩል ደረጃ የሚያጠነክር ፕሮግራም ነው።"
            )
    else:
        # Male Profiles
        if goal == "MUSCLE_GAIN":
            goal_title = "💪 Muscle Hypertrophy (ደረትና ክንድ ማሳደግ)"
            focus_notes = (
                f"• ለእርስዎ {int(weight)} kg ክብደት በየቀኑ ቢያንስ ~{daily_protein}g ፕሮቲን መውሰድ አለብዎት።\n"
                "• በሳምንት {days} ቀናት Compound እንቅስቃሴዎች (ደረት፣ ጀርባና እግር) ላይ Progressive Overload እንሰራለን።\n"
                "• ለእድገትዎ በየቀኑ ቢያንስ 7-8 ሰዓት ጥራት ያለው እንቅልፍ ወሳኝ ነው።"
            )
        elif goal == "FAT_LOSS":
            goal_title = "🔥 Fat Loss & Shred (ቦርጭ ማጥፋትና መድረቅ)"
            focus_notes = (
                f"• የጡንቻ መጠን ሳይቀንስ ቦርጭን ለማጥፋት በቀን ~{daily_protein}g ፕሮቲን እየወሰዱ የክብደት ልምምድ ማድረግ።\n"
                "• በሳምንት 2-3 ቀናት ከልምምድ በኋላ የ 20 ደቂቃ Incline Cardio ማካተት።"
            )
        else:
            goal_title = "⚡ Strength & Power (ጥንካሬና ብቃት)"
            focus_notes = (
                f"• በሳምንት {days} ቀናት የሰውነትን አጠቃላይ ጥንካሬና ሃይል የሚያዳብሩ ከባባድ እንቅስቃሴዎች ላይ ማተኮር።\n"
                "• በእያንዳንዱ ከባድ Set መካከል የ 2-3 ደቂቃ እረፍት መውሰድ።"
            )

    card = (
        "✨ **ይሄው የእርስዎ የግል የአካል ብቃት ማጠቃለያ ደርሷል!**\n\n"
        f"**> 📋 የአትሌት ማጠቃለያ // {client_code}\n"
        f"• ጾታ: {gender_label} | እድሜ: {age} | ክብደት: {int(weight)} kg\n"
        f"• ዋና ግብ: {goal_title}\n"
        f"• የትሬኒንግ ስፕሊት: {split_desc}\n"
        f"• ደረጃ: {level_label}**\n\n"
        "💡 **የብሩክታዊት ምክርና የትኩረት ነጥቦች:**\n"
        f"{focus_notes}\n\n"
        f"💧 **ዕለታዊ የውሃ መጠን:** በቀን ~{water_liters} ሊትር\n"
        f"🥩 **ዕለታዊ የፕሮቲን ኢላማ:** በቀን ~{daily_protein}g"
    )
    return card

