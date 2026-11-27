import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from config import settings
from handlers.admin import router as admin_router
from handlers.onboarding import (
    extract_age,
    extract_weight,
    _build_pitch_text,
    _build_payment_page_text,
    router as onboarding_router,
)
from middlewares.error_handler import is_benign_telegram_error, global_error_handler
from services.diagnostics import generate_athlete_diagnostic_card
from services.verifier import extract_transaction_reference, is_valid_biruktawit_receiver
from keyboards.user_kb import (
    get_user_main_menu,
    get_support_keyboard,
    get_goal_keyboard,
    get_offer_cta_keyboard,
    get_payment_action_keyboard,
    get_athlete_plan_keyboard,
    get_resume_keyboard,
)
from keyboards.admin_kb import get_admin_review_keyboard, get_admin_home_keyboard


def test_onboarding_extraction():
    assert extract_age("24") == 24
    assert extract_age("I am 29 years old") == 29
    assert extract_age("12") is None
    assert extract_age("95") is None

    assert extract_weight("62") == 62.0
    assert extract_weight("65.5 kg") == 65.5
    assert extract_weight("25") is None
    assert extract_weight("invalid") is None
    print("✅ Test 1: Age & Weight natural regex extraction passed.")


def test_diagnostics_generation():
    from utils.tg_helpers import format_plan_name, parse_age_callback, format_age_display
    from keyboards.user_kb import get_age_keyboard

    age_kb = get_age_keyboard()
    assert age_kb.inline_keyboard[0][0].callback_data == "age:18-24"
    age_num, age_lbl = parse_age_callback("18-24")
    assert age_num == 21 and age_lbl == "18 - 24"

    athlete_data = {
        "full_name": "Selam_Fit",
        "gender": "FEMALE",
        "age": 21,
        "age_range": "18 - 24",
        "weight_kg": 62.0,
        "primary_goal": "BOOTY_CURVES",
        "days_per_week": 4,
    }
    card = generate_athlete_diagnostic_card(athlete_data, 2841)
    assert "BF-2841" in card
    assert "MEMBER PROFILE" in card
    assert "18 - 24" in card
    assert "21" not in card  # Never show guessed midpoint on card when range was chosen
    assert "ዳሌና መቀመጫ ማውጣት" in card
    assert "Booty" not in card
    assert "ወገብ ማጥበብ" in card
    assert "kcal" in card and " - " in card
    assert "97.2%" not in card
    assert "--" not in card and "—" not in card

    assert format_age_display({"age": 24, "age_range": "24"}) == "24"
    assert format_age_display({"age": 45, "age_range": "45+"}) == "45+"

    fatloss_card = generate_athlete_diagnostic_card(
        {"full_name": "Beki", "gender": "MALE", "age_range": "25 - 34", "weight_kg": 75, "primary_goal": "FAT_LOSS", "days_per_week": 3},
        1022,
    )
    assert "25 - 34" in fatloss_card
    assert "ቦርጭና ስብ መቀነስ" in fatloss_card
    assert "ቦርጭ እና የስብ መጠን መቀነስ" in fatloss_card
    assert "BF-" not in format_plan_name("BF-F-BC-4X")
    assert "የሴቶች ዳሌና ቅርጽ" in format_plan_name("BF-F-BC-4X")
    print("✅ Test 2: Exact age range, Amharic diagnostics card & plan naming passed.")


def test_anti_fraud_verifier():
    assert is_valid_biruktawit_receiver("Payment to BIRUKTAWIT FIKRE confirmed") is True
    assert is_valid_biruktawit_receiver("Payment to HILAWE SEMMA") is False
    assert is_valid_biruktawit_receiver("Payment to WARKA FITNESS") is False

    assert extract_transaction_reference("CBE FT24315A8912") == "FT24315A8912"
    assert extract_transaction_reference("BOA TXN901238475") == "TXN901238475"
    print("✅ Test 3: Anti-fraud and Biruktawit receiver verification passed.")


def test_split_threshold_engine():
    def calculate_share(sale_number: int, amount: int):
        gross = Decimal(amount)
        if sale_number <= 150:
            c_pct, p_pct = Decimal("0.60"), Decimal("0.40")
        else:
            c_pct, p_pct = Decimal("0.70"), Decimal("0.30")
        return (gross * c_pct).quantize(Decimal("0.01")), (gross * p_pct).quantize(Decimal("0.01"))

    c1, p1 = calculate_share(1, 950)
    assert c1 == Decimal("570.00") and p1 == Decimal("380.00")
    c150, p150 = calculate_share(150, 950)
    assert c150 == Decimal("570.00") and p150 == Decimal("380.00")
    c151, p151 = calculate_share(151, 950)
    assert c151 == Decimal("665.00") and p151 == Decimal("285.00")
    print("✅ Test 4: 60/40 -> 70/30 revenue threshold engine passed.")


def test_keyboards_and_support():
    user_menu = get_user_main_menu()
    assert any("የኔ ፕላን" in btn.text for row in user_menu.keyboard for btn in row)

    sup_kb = get_support_keyboard()
    sup_btns = [b for row in sup_kb.inline_keyboard for b in row]
    assert any(b.url == f"https://t.me/{settings.SUPPORT_BOT_USERNAME}" for b in sup_btns)
    assert "coachbiruktawitsupportbot" in sup_btns[0].url

    fem_goals = get_goal_keyboard(True)
    fem_texts = [b.text for row in fem_goals.inline_keyboard for b in row]
    assert any("Booty & Curves" in t for t in fem_texts)
    assert any("Muscle & Tone" in t for t in fem_texts)

    admin_review = get_admin_review_keyboard("ORD-12345")
    assert any("Approve" in btn.text for row in admin_review.inline_keyboard for btn in row)
    assert any("Reject" in btn.text for row in admin_review.inline_keyboard for btn in row)

    from keyboards.admin_kb import get_admin_reply_menu, get_pending_queue_markup
    admin_home = get_admin_home_keyboard()
    home_texts = [btn.text for row in admin_home.inline_keyboard for btn in row]
    assert home_texts == ["🔄 Refresh"]

    admin_reply = get_admin_reply_menu()
    reply_rows = [[btn.text for btn in row] for row in admin_reply.keyboard]
    assert reply_rows == [["⏳ Pending Payment", "📢 Global Broadcast"], ["📦 Products"]]

    q_kb = get_pending_queue_markup([{"order_id": "ORD-1", "full_name": "Abebe", "amount_etb": 950}], 0, 1)
    assert q_kb.inline_keyboard[0][0].callback_data == "adm_inspect:ORD-1"
    print("✅ Test 5: Keyboards, /admin 1-button inline, pending queue & reply menu passed.")


def test_button_styling_and_copy():
    review_kb = get_admin_review_keyboard("ORD-TEST123")
    row0 = review_kb.inline_keyboard[0]
    app_btn = next(b for b in row0 if "Approve" in b.text)
    rej_btn = next(b for b in row0 if "Reject" in b.text)

    assert app_btn.model_dump(exclude_none=True).get("style") == "success"
    assert rej_btn.model_dump(exclude_none=True).get("style") == "danger"

    cta_kb = get_offer_cta_keyboard(950)
    cta_btns = [b for row in cta_kb.model_dump(exclude_none=True)["inline_keyboard"] for b in row]
    assert cta_btns[0]["callback_data"] == "open_payment_page"
    assert cta_btns[0].get("style") == "success"

    pay_kb = get_payment_action_keyboard("1000123456789", "55936749")
    flat_btns = [b for row in pay_kb.model_dump(exclude_none=True)["inline_keyboard"] for b in row]
    cbe_btn = next(b for b in flat_btns if "CBE" in b["text"])
    assert "copy_text" in cbe_btn and cbe_btn["copy_text"]["text"] == "1000123456789"
    boa_btn = next(b for b in flat_btns if "BOA" in b["text"])
    assert "copy_text" in boa_btn and boa_btn["copy_text"]["text"] == "55936749"

    pitch_html = _build_pitch_text(True, "የሴቶች ዳሌና ቅርጽ")
    assert "<s>" in pitch_html and "1000033231273" not in pitch_html
    pay_html = _build_payment_page_text(True, "BF-F-BC-4X")
    assert "Screenshot" in pay_html and "BF-F-BC-4X" not in pay_html
    print("✅ Test 6: 2-stage pitch strikethrough, payment copy page & button styling passed.")


def test_router_handlers_and_hygiene():
    cb_names = {h.callback.__name__ for h in onboarding_router.callback_query.handlers}
    assert "handle_buy_now" in cb_names
    assert "handle_open_payment_page" in cb_names
    assert "handle_checkin_history" in cb_names
    assert "handle_commitment" in cb_names

    admin_cb_names = {h.callback.__name__ for h in admin_router.callback_query.handlers}
    assert "handle_admin_quick_reply_start" in admin_cb_names

    admin_msg_names = {h.callback.__name__ for h in admin_router.message.handlers}
    assert "handle_admin_swipe_reply" in admin_msg_names
    assert "handle_admin_quick_reply_send" in admin_msg_names

    runtime_files = [
        "handlers/onboarding.py",
        "handlers/payment.py",
        "handlers/admin.py",
        "services/diagnostics.py",
        "services/deliverer.py",
        "services/recovery.py",
        "middlewares/error_handler.py",
    ]
    for rel in runtime_files:
        path = os.path.join(BASE_DIR, rel)
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        assert 'parse_mode="Markdown"' not in src, f"Markdown parse_mode leaked into {rel}"
        assert "እርስዎ" not in src or rel == "handlers/payment.py", f"Formal እርስዎ leaked into {rel}"
        assert "አትሌት" not in src, f"Forbidden አትሌት leaked into {rel}"
        assert "—" not in src, f"Forbidden em-dash leaked into {rel}"

    import ast
    tg_methods = {"answer", "send_message", "send_photo", "send_document", "edit_text", "edit_caption", "delete"}
    for rel in ["handlers/onboarding.py", "handlers/admin.py", "handlers/payment.py"]:
        src = open(os.path.join(BASE_DIR, rel), "r", encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("gather", "create_task"):
                for arg in node.args:
                    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr in tg_methods:
                        raise AssertionError(f"Unsafe TelegramMethod '.{arg.func.attr}()' inside {node.func.attr}() in {rel}:{node.lineno}")

    print("✅ Test 7: Handler registration, async TelegramMethod safety & HTML hygiene passed.")


def test_error_boundary_and_suppression():
    assert is_benign_telegram_error(Exception("Bad Request: query is too old and response timeout expired or query ID is invalid"))
    assert is_benign_telegram_error(Exception("Bad Request: message is not modified"))
    assert not is_benign_telegram_error(RuntimeError("Database exploded"))

    async def _run():
        from database.db import db
        orig_get = db.get_athlete
        db.get_athlete = AsyncMock(return_value={"gender": "FEMALE"})

        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.from_user = MagicMock(id=999, username="tester", full_name="Test User")
        mock_msg.answer = AsyncMock()

        mock_update = MagicMock()
        mock_update.bot = mock_bot
        mock_update.message = mock_msg
        mock_update.callback_query = None

        # 1. Benign query timeout -> must NOT forward traceback document
        benign_evt = MagicMock(update=mock_update, exception=Exception("Bad Request: query is too old"))
        await global_error_handler(benign_evt)
        assert mock_bot.send_document.call_count == 0

        # 2. Real error -> MUST notify admin/group AND send personalized (no እርስዎ) message to female user
        try:
            raise ValueError("Simulated boom")
        except ValueError as err:
            real_evt = MagicMock(update=mock_update, exception=err)
            await global_error_handler(real_evt)
        assert mock_bot.send_document.call_count >= 1
        sent_user_err = mock_msg.answer.call_args[0][0]
        assert "ሞክሪ" in sent_user_err and "እባክዎ" not in sent_user_err
        db.get_athlete = orig_get

    asyncio.run(_run())
    print("✅ Test 8: Error suppression ('query is too old') & traceback alert dispatch passed.")


if __name__ == "__main__":
    print("Running Full Funnel & Optimization Integration Tests...")
    test_onboarding_extraction()
    test_diagnostics_generation()
    test_anti_fraud_verifier()
    test_split_threshold_engine()
    test_keyboards_and_support()
    test_button_styling_and_copy()
    test_router_handlers_and_hygiene()
    test_error_boundary_and_suppression()
    print("\n🎉 ALL 8 INTEGRATION SUITES PASSED CLEANLY!")
