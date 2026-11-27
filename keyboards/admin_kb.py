from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


# -------------------------------------------------------------
# Receipt Review Inline Keyboard
# -------------------------------------------------------------
def get_admin_review_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Compact receipt review buttons with native Bot API color styling."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"adm_app:{order_id}", style="success")
    builder.button(text="❌ Reject", callback_data=f"adm_rej:{order_id}", style="danger")
    builder.adjust(2)
    return builder.as_markup()


# -------------------------------------------------------------
# Main Admin Reply Keyboard (Bottom Persistent Menu)
# -------------------------------------------------------------
def get_admin_reply_menu() -> ReplyKeyboardMarkup:
    """Compact 2-row admin bottom menu."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="⏳ Pending Payment")
    builder.button(text="📢 Global Broadcast")
    builder.button(text="📦 Products")
    builder.adjust(2, 1)
    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Admin Menu...",
    )


# -------------------------------------------------------------
# Single Inline Button Under /admin Card (Refresh Only)
# -------------------------------------------------------------
def get_admin_home_keyboard() -> InlineKeyboardMarkup:
    """Refresh button under /admin daily summary card."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Refresh", callback_data="adm_refresh_stats", style="success")
    builder.adjust(1)
    return builder.as_markup()


def get_pending_queue_markup(orders: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """CoachHilawe-style paginated pending payment queue inline buttons."""
    builder = InlineKeyboardBuilder()
    for row in orders:
        name = (row.get("full_name") or "Member")[:18]
        amount = row.get("amount_etb", 950)
        builder.button(text=f"🧾 {name} — {amount} ETB", callback_data=f"adm_inspect:{row['order_id']}")
    builder.adjust(1)

    nav = []
    if page > 0:
        builder.button(text="⬅️ Prev", callback_data=f"paypage:{page - 1}")
        nav.append(1)
    if total_pages > 1:
        builder.button(text=f"📄 {page + 1}/{total_pages}", callback_data="noop_page")
        nav.append(1)
    if page + 1 < total_pages:
        builder.button(text="Next ➡️", callback_data=f"paypage:{page + 1}")
        nav.append(1)

    if nav:
        rows = [1] * len(orders) + [len(nav)]
        builder.adjust(*rows)
    return builder.as_markup()


def get_admin_catalog_keyboard() -> InlineKeyboardMarkup:
    """Back button for product inspection view."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back to Dashboard", callback_data="adm_home")
    builder.adjust(1)
    return builder.as_markup()
