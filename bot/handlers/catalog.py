from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.db import AsyncSessionLocal
from database.crud import (
    get_all_categories, get_category_by_id,
    get_products_by_category, get_product_by_id
)

router = Router()

# ─── Price formatter ──────────────────────────────────────────────────────────
def format_price(product) -> str:
    if product.discount_percent > 0:
        old = f"{int(product.price):,}"
        new = f"{int(product.final_price):,}"
        return f"<s>{old}</s> → <b>{new} so'm</b> 🔥 -{int(product.discount_percent)}%"
    return f"<b>{int(product.price):,} so'm</b>"


# ─── Keyboards ────────────────────────────────────────────────────────────────
def categories_kb(categories) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{cat.emoji} {cat.name}",
        callback_data=f"cat_{cat.id}"
    )] for cat in categories]
    rows.append([InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_kb(products, category_id: int) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        price_str = f"{int(p.final_price):,} so'm"
        if p.discount_percent > 0:
            price_str += f" (-{int(p.discount_percent)}%)"
        stock = "" if p.in_stock else " ❌"
        rows.append([InlineKeyboardButton(
            text=f"{p.name}{stock} — {price_str}",
            callback_data=f"prod_{p.id}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_detail_kb(product) -> InlineKeyboardMarkup:
    rows = []
    if product.in_stock:
        rows.append([InlineKeyboardButton(
            text="🛒 Savatga qo'shish",
            callback_data=f"add_cart_{product.id}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{product.category_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def size_kb(product_id: int) -> InlineKeyboardMarkup:
    sizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]
    rows, row = [], []
    for s in sizes:
        row.append(InlineKeyboardButton(text=s, callback_data=f"size_{product_id}_{s}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Bekor", callback_data=f"cat_{product_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Handlers ─────────────────────────────────────────────────────────────────
@router.message(F.text == "🛍 Katalog")
async def show_catalog(message: Message):
    async with AsyncSessionLocal() as session:
        categories = await get_all_categories(session)
    if not categories:
        await message.answer("😕 Hozircha mahsulotlar mavjud emas.")
        return
    await message.answer(
        "🛍 <b>Kategoriyani tanlang:</b>",
        parse_mode="HTML",
        reply_markup=categories_kb(categories)
    )


@router.callback_query(F.data == "catalog")
async def callback_catalog(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        categories = await get_all_categories(session)
    try:
        await callback.message.edit_text(
            "🛍 <b>Kategoriyani tanlang:</b>",
            parse_mode="HTML",
            reply_markup=categories_kb(categories)
        )
    except:
        await callback.message.answer(
            "🛍 <b>Kategoriyani tanlang:</b>",
            parse_mode="HTML",
            reply_markup=categories_kb(categories)
        )


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    from bot.middlewares.admin_check import is_admin
    from bot.keyboards.main_menu import main_menu_kb
    admin = is_admin(callback.from_user.id)
    await callback.message.answer("🏠 Asosiy menyu", reply_markup=main_menu_kb(is_admin=admin))
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def show_category_products(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        category = await get_category_by_id(session, category_id)
        products = await get_products_by_category(session, category_id)

    if not products:
        await callback.answer("😕 Bu kategoriyada hozircha mahsulot yo'q", show_alert=True)
        return

    text = f"{category.emoji} <b>{category.name}</b>\n"
    if category.description:
        text += f"\n📝 {category.description}\n"
    text += f"\n📦 {len(products)} ta mahsulot\n\nTanlang 👇"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=products_kb(products, category_id))
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=products_kb(products, category_id))


@router.callback_query(F.data.startswith("prod_"))
async def show_product_detail(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    if not product:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    text = f"<b>{product.name}</b>\n\n"
    if product.description:
        text += f"📝 {product.description}\n\n"
    text += f"💰 Narxi: {format_price(product)}\n"

    if not product.in_stock:
        text += "\n⚠️ <i>Hozircha mavjud emas</i>"

    # Ism yozish xizmati uchun maxsus izoh
    if product.category_id == 4:
        text += "\n\n✍️ <i>Buyurtma bergandan so'ng ism va raqam so'raladi</i>"

    kb = product_detail_kb(product)

    if product.photo_url:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer_photo(
            photo=product.photo_url,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("add_cart_"))
async def ask_size_or_add(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    # Ism yozish xizmati — o'lcham kerak emas, to'g'ri FSM ga
    if product.category_id == 4:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, None, state)
        return

    # Boshqa kategoriyalar — o'lcham tanlash
    try:
        await callback.message.edit_reply_markup(reply_markup=size_kb(product_id))
    except:
        await callback.message.answer("📏 O'lchamni tanlang:", reply_markup=size_kb(product_id))
    await callback.answer("📏 O'lchamni tanlang 👇")
