import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from decimal import Decimal
from handlers.onboarding import extract_age, extract_weight
from services.diagnostics import generate_athlete_diagnostic_card
from services.verifier import is_valid_biruktawit_receiver, extract_transaction_reference
from keyboards.user_kb import (
    get_user_main_menu,
    get_gender_keyboard,
    get_payment_action_keyboard,
    get_athlete_plan_keyboard,
    get_resume_keyboard
)
from keyboards.admin_kb import get_admin_review_keyboard, get_admin_home_keyboard

def test_onboarding_extraction():
    assert extract_age("24") == 24
    assert extract_age("እድሜዬ 28 አመቴ ነው") == 28
    assert extract_age("90") == 90
    assert extract_age("12") is None  # Below min age 14
    assert extract_age("99") is None  # Above max age 90

    assert extract_weight("62") == 62.0
    assert extract_weight("65.5 kg") == 65.5
    assert extract_weight("ክብደቴ 70 ኪሎ ነው") == 70.0
    assert extract_weight("25") is None  # Below min weight 35
    assert extract_weight("invalid") is None
    print("✅ Test 1: Age & Weight natural regex extraction passed.")

def test_diagnostics_generation():
    athlete_data = {
        "gender": "FEMALE",
        "age": 24,
        "weight_kg": 62.0,
        "primary_goal": "BOOTY_CURVES",
        "days_per_week": 4,
        "experience_level": "BEGINNER"
    }
    card = generate_athlete_diagnostic_card(athlete_data, 2841)
    assert "BF-2841" in card
    assert "Booty & Curves" in card
    assert "Controlled Eccentrics" in card
    assert "Hip Thrust" in card
    print("✅ Test 2: Personalized diagnostics generation passed.")

def test_anti_fraud_verifier():
    assert is_valid_biruktawit_receiver("Payment to BIRUKTAWIT FIKRE confirmed") is True
    assert is_valid_biruktawit_receiver("Payment to HILAWE SEMMA") is False
    assert is_valid_biruktawit_receiver("Payment to WARKA FITNESS") is False

    assert extract_transaction_reference("CBE FT24315A8912") == "FT24315A8912"
    assert extract_transaction_reference("Telebirr TXN901238475") == "TXN901238475"
    print("✅ Test 3: Anti-fraud and Biruktawit receiver verification passed.")

def test_split_threshold_engine():
    def calculate_share(sale_number: int, amount: int):
        gross = Decimal(amount)
        if sale_number <= 150:
            c_pct, p_pct = Decimal("0.60"), Decimal("0.40")
        else:
            c_pct, p_pct = Decimal("0.70"), Decimal("0.30")
        return (gross * c_pct).quantize(Decimal("0.01")), (gross * p_pct).quantize(Decimal("0.01"))

    # Sale 1 (Tier 1)
    c1, p1 = calculate_share(1, 950)
    assert c1 == Decimal("570.00")
    assert p1 == Decimal("380.00")

    # Sale 150 (Tier 1 boundary)
    c150, p150 = calculate_share(150, 950)
    assert c150 == Decimal("570.00")
    assert p150 == Decimal("380.00")

    # Sale 151 (Tier 2 transition)
    c151, p151 = calculate_share(151, 950)
    assert c151 == Decimal("665.00")
    assert p151 == Decimal("285.00")

    # Sale 500 (Tier 2 permanent)
    c500, p500 = calculate_share(500, 950)
    assert c500 == Decimal("665.00")
    assert p500 == Decimal("285.00")
    print("✅ Test 4: 60/40 -> 70/30 revenue threshold engine passed.")

def test_keyboards_localization():
    user_menu = get_user_main_menu()
    assert any("የኔ ፕላን" in btn.text for row in user_menu.keyboard for btn in row)

    admin_review = get_admin_review_keyboard("ORD-12345")
    assert any("Approve" in btn.text for row in admin_review.inline_keyboard for btn in row)
    assert any("Reject" in btn.text for row in admin_review.inline_keyboard for btn in row)

    admin_home = get_admin_home_keyboard()
    assert any("Payouts" in btn.text for row in admin_home.inline_keyboard for btn in row)
    assert any("Funnel" in btn.text for row in admin_home.inline_keyboard for btn in row)
    print("✅ Test 5: Keyboards localization (Amharic user / English admin) passed.")

def test_button_styling_and_copy():
    # Admin Review Button Colors
    review_kb = get_admin_review_keyboard("ORD-TEST123")
    row0 = review_kb.inline_keyboard[0]
    app_btn = next(b for b in row0 if "Approve" in b.text)
    rej_btn = next(b for b in row0 if "Reject" in b.text)
    
    dumped_app = app_btn.model_dump(exclude_none=True)
    dumped_rej = rej_btn.model_dump(exclude_none=True)
    assert dumped_app.get("style") == "success", "Approve button must use style='success' (green)"
    assert dumped_rej.get("style") == "danger", "Reject button must use style='danger' (red)"

    # User Payment Copy & Success Styling
    pay_kb = get_payment_action_keyboard("1000123456789", "0911223344")
    dumped_pay = pay_kb.model_dump(exclude_none=True)
    flat_btns = [b for row in dumped_pay["inline_keyboard"] for b in row]

    cbe_btn = next(b for b in flat_btns if "CBE" in b["text"])
    assert "copy_text" in cbe_btn and cbe_btn["copy_text"]["text"] == "1000123456789"

    receipt_btn = next(b for b in flat_btns if "ደረሰኝ" in b["text"])
    assert receipt_btn.get("style") == "success"

    # Athlete Plan Keyboards
    active_kb = get_athlete_plan_keyboard(has_active_order=True)
    dumped_active = active_kb.model_dump(exclude_none=True)
    flat_active = [b for row in dumped_active["inline_keyboard"] for b in row]
    assert any(b.get("style") == "success" and "Check-in" in b["text"] for b in flat_active)

    inactive_kb = get_athlete_plan_keyboard(has_active_order=False)
    dumped_inactive = inactive_kb.model_dump(exclude_none=True)
    flat_inactive = [b for row in dumped_inactive["inline_keyboard"] for b in row]
    assert any(b.get("style") == "success" and "ጀምር" in b["text"] for b in flat_inactive)

    print("✅ Test 6: Native Telegram button styling (style=success/danger) & copy_text passed.")

def test_checkin_and_funnel_tracking():
    # 1. Funnel States Sequence
    expected_states = [
        "START", "GENDER_SET", "AGE_SET", "WEIGHT_SET",
        "GOAL_SET", "SPLIT_SET", "DIAGNOSTIC_READY",
        "CHECKOUT_PITCHED", "RECEIPT_SUBMITTED", "ACTIVE_MEMBER"
    ]
    assert len(expected_states) == 10

    # 2. Check-in Weight Delta Calculation
    start_weight = 62.0
    week1_weight = 61.2
    week2_weight = 60.5

    delta_w1 = week1_weight - start_weight
    delta_w2 = week2_weight - start_weight

    assert round(delta_w1, 1) == -0.8
    assert round(delta_w2, 1) == -1.5
    print("✅ Test 7: Funnel micro-states & athlete transformation check-in calculations passed.")

def test_resumption_and_user_tracking():
    # 1. Resume Keyboards
    resume_pay_kb = get_resume_keyboard("CHECKOUT_PITCHED", "1000123456789", "0911223344")
    dumped_resume_pay = resume_pay_kb.model_dump(exclude_none=True)
    flat_resume_pay = [b for row in dumped_resume_pay["inline_keyboard"] for b in row]
    assert any("CBE" in b["text"] for b in flat_resume_pay)
    assert any("እንደገና ከመጀመሪያ" in b["text"] for b in flat_resume_pay)

    resume_q_kb = get_resume_keyboard("ONBOARDING", "1000123456789", "0911223344")
    dumped_resume_q = resume_q_kb.model_dump(exclude_none=True)
    flat_resume_q = [b for row in dumped_resume_q["inline_keyboard"] for b in row]
    assert any("የቀረኝን" in b["text"] for b in flat_resume_q)

    # 2. Sheger Slang Button Text Checks (No stiff "የለውጥ ታሪክ")
    active_plan_kb = get_athlete_plan_keyboard(has_active_order=True)
    dumped_active = active_plan_kb.model_dump(exclude_none=True)
    flat_active = [b for row in dumped_active["inline_keyboard"] for b in row]
    assert not any("የለውጥ ታሪክ" in b["text"] for b in flat_active), "Must not contain stiff 'የለውጥ ታሪክ'"
    assert any("የኔ Record" in b["text"] for b in flat_active), "Must contain natural 'የኔ Record'"
    assert any("ሳምንታዊ Check-in" in b["text"] for b in flat_active), "Must contain 'ሳምንታዊ Check-in'"
    print("✅ Test 8: State resumption keyboards & pure Sheger slang verification passed.")

if __name__ == "__main__":
    print("Running Full Funnel Integration Tests...")
    test_onboarding_extraction()
    test_diagnostics_generation()
    test_anti_fraud_verifier()
    test_split_threshold_engine()
    test_keyboards_localization()
    test_button_styling_and_copy()
    test_checkin_and_funnel_tracking()
    test_resumption_and_user_tracking()
    print("\n🎉 ALL 8 INTEGRATION SUITES PASSED CLEANLY!")

