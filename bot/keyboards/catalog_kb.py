from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Category, Product


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(
                text=f"{cat.emoji} {cat.name}",
                callback_data=f"cat_{cat.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_kb(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        price_text = f"{int(prod.final_price):,} so'm"
        if prod.discount_percent > 0:
            price_text += f" (-{int(prod.discount_percent)}%)"
        buttons.append([
            InlineKeyboardButton(
                text=f"{prod.name} — {price_text}",
                callback_data=f"prod_{prod.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_kb(product: Product) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛒 Savatga qo'shish", callback_data=f"add_cart_{product.id}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{product.category_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def size_kb(product_id: int) -> InlineKeyboardMarkup:
    sizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]
    buttons = []
    row = []
    for i, size in enumerate(sizes):
        row.append(InlineKeyboardButton(
            text=size,
            callback_data=f"size_{product_id}_{size}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Savatni tozalash", callback_data="clear_cart")],
        [InlineKeyboardButton(text="🛍 Katalogga qaytish", callback_data="catalog")],
    ])


def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order"),
            InlineKeyboardButton(text="❌ Bekor", callback_data="cancel_order"),
        ]
    ])
