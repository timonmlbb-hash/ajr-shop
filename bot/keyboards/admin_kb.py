from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.models import Order


def admin_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Yangi buyurtmalar"), KeyboardButton(text="📊 Barcha buyurtmalar")],
            [KeyboardButton(text="➕ Mahsulot qo'shish"), KeyboardButton(text="📦 Mahsulotlar")],
            [KeyboardButton(text="🌐 Web Panel"), KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True
    )


def order_actions_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_confirm_{order_id}"),
            InlineKeyboardButton(text="🚚 Yetkazilmoqda", callback_data=f"admin_deliver_{order_id}"),
        ],
        [
            InlineKeyboardButton(text="✔️ Yetkazildi", callback_data=f"admin_done_{order_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"admin_cancel_{order_id}"),
        ],
    ])


def product_manage_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Narxni o'zgartirish", callback_data=f"edit_price_{product_id}"),
            InlineKeyboardButton(text="🏷 Skidka", callback_data=f"edit_discount_{product_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_prod_{product_id}"),
        ]
    ])
