from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# -------------------------------------------------------------
# Admin Keyboards (Short, Clean & Punchy English)
# -------------------------------------------------------------
def get_admin_review_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """
    Compact receipt review buttons with native Bot API color styling.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"adm_app:{order_id}", style="success")
    builder.button(text="❌ Reject", callback_data=f"adm_rej:{order_id}", style="danger")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_home_keyboard() -> InlineKeyboardMarkup:
    """
    Admin control panel main menu.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Payouts", callback_data="adm_view_payouts", style="primary")
    builder.button(text="📈 Funnel", callback_data="adm_view_funnel", style="primary")
    builder.button(text="👥 Users", callback_data="adm_view_users", style="primary")
    builder.button(text="💰 Settle", callback_data="adm_settle_balance")
    builder.button(text="📦 Catalog", callback_data="adm_view_catalog")
    builder.button(text="🔄 Refresh", callback_data="adm_refresh_stats")
    builder.adjust(2, 2, 2)
    return builder.as_markup()

def get_admin_catalog_keyboard() -> InlineKeyboardMarkup:
    """
    Catalog inspection keyboard.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Payouts", callback_data="adm_view_payouts")
    builder.button(text="🔙 Back", callback_data="adm_home")
    builder.adjust(2)
    return builder.as_markup()
