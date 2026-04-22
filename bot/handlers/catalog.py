from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.db import AsyncSessionLocal
from database.crud import (
    get_all_categories, get_category_by_id,
    get_products_by_category, get_product_by_id
)

router = Router()

# Forma kategoriyalari ID lari (1=Formalar, 2=Retro formalar)
FORMA_CATEGORIES = [1, 2]

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
    """
    1-o'zgarish: Savatga qo'shish + To'g'ridan buyurtma berish
    """
    rows = []
    if product.in_stock:
        rows.append([
            InlineKeyboardButton(text="🛒 Savatga", callback_data=f"add_cart_{product.id}"),
            InlineKeyboardButton(text="⚡ Buyurtma berish", callback_data=f"buy_now_{product.id}"),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{product.category_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def size_kb(product_id: int, buy_now: bool = False) -> InlineKeyboardMarkup:
    sizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]
    prefix = "buynow_size" if buy_now else "size"
    rows, row = [], []
    for s in sizes:
        row.append(InlineKeyboardButton(text=s, callback_data=f"{prefix}_{product_id}_{s}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Bekor", callback_data=f"cat_{product_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_print_kb(product_id: int, buy_now: bool = False) -> InlineKeyboardMarkup:
    """2-o'zgarish: Forma orqasiga ism yozish so'rovi (+50.000 so'm)"""
    prefix = "buynow" if buy_now else "cart"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha (+50,000 so'm)", callback_data=f"{prefix}_print_yes_{product_id}"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data=f"{prefix}_print_no_{product_id}"),
        ]
    ])


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

    if product.category_id in FORMA_CATEGORIES:
        text += "\n\n✍️ <i>Forma orqasiga ism yozish: +50,000 so'm</i>"

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


# ─── SAVATGA QO'SHISH ─────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("add_cart_"))
async def ask_size_or_add(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    if product.category_id == 4:  # Ism yozish xizmati
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, None, state)
        return

    # O'lcham tanlash
    try:
        await callback.message.edit_reply_markup(reply_markup=size_kb(product_id, buy_now=False))
    except:
        await callback.message.answer("📏 O'lchamni tanlang:", reply_markup=size_kb(product_id, buy_now=False))
    await callback.answer("📏 O'lchamni tanlang 👇")


@router.callback_query(F.data.startswith("size_"))
async def handle_size_cart(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    product_id = int(parts[1])
    size = parts[2]

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    # Forma kategoriyasida — ism yozish so'raymiz
    if product.category_id in FORMA_CATEGORIES:
        await state.update_data(pending_product_id=product_id, pending_size=size, pending_mode="cart")
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption + f"\n\n📏 O'lcham: <b>{size}</b>",
                parse_mode="HTML",
                reply_markup=back_print_kb(product_id, buy_now=False)
            )
        except:
            try:
                await callback.message.edit_reply_markup(reply_markup=back_print_kb(product_id, buy_now=False))
            except:
                await callback.message.answer(
                    f"✍️ Forma orqasiga <b>ism va raqam</b> yozdirasizmi?\n"
                    f"<i>+50,000 so'm qo'shiladi</i>",
                    parse_mode="HTML",
                    reply_markup=back_print_kb(product_id, buy_now=False)
                )
        await callback.answer(f"✅ O'lcham: {size}")
    else:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, size, state)


# ─── ORQAGA ISM YOZISH — HA/YO'Q ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("cart_print_yes_"))
async def cart_print_yes(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    size = data.get("pending_size")

    await state.update_data(print_product_id=product_id, print_size=size, print_mode="cart")
    from bot.handlers.cart import PrintNameState
    await state.set_state(PrintNameState.waiting_name)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer(
        "✍️ <b>Forma orqasiga yoziladigan ism va raqamni kiriting:</b>\n\n"
        "<i>Masalan: HUSANOV 45</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cart_print_no_"))
async def cart_print_no(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    size = data.get("pending_size")
    await state.update_data(pending_product_id=None, pending_size=None)

    from bot.handlers.cart import add_to_cart_direct
    await add_to_cart_direct(callback, product_id, size, state)


# ─── TO'G'RIDAN BUYURTMA (BUY NOW) ───────────────────────────────────────────
@router.callback_query(F.data.startswith("buy_now_"))
async def buy_now(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    if product.category_id == 4:
        # Ism yozish xizmati — avval FSM
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, None, state)
        await state.update_data(buy_now_after=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=size_kb(product_id, buy_now=True))
    except:
        await callback.message.answer("📏 O'lchamni tanlang:", reply_markup=size_kb(product_id, buy_now=True))
    await callback.answer("📏 O'lchamni tanlang 👇")


@router.callback_query(F.data.startswith("buynow_size_"))
async def handle_size_buynow(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 3)
    product_id = int(parts[2])
    size = parts[3]

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    if product.category_id in FORMA_CATEGORIES:
        await state.update_data(pending_product_id=product_id, pending_size=size, pending_mode="buynow")
        try:
            await callback.message.edit_reply_markup(reply_markup=back_print_kb(product_id, buy_now=True))
        except:
            await callback.message.answer(
                f"✍️ Forma orqasiga <b>ism va raqam</b> yozdirasizmi?\n<i>+50,000 so'm</i>",
                parse_mode="HTML",
                reply_markup=back_print_kb(product_id, buy_now=True)
            )
        await callback.answer(f"✅ O'lcham: {size}")
    else:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, size, state)
        await _go_to_checkout(callback, state)


@router.callback_query(F.data.startswith("buynow_print_yes_"))
async def buynow_print_yes(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    size = data.get("pending_size")
    await state.update_data(print_product_id=product_id, print_size=size, print_mode="buynow")
    from bot.handlers.cart import PrintNameState
    await state.set_state(PrintNameState.waiting_name)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer(
        "✍️ <b>Ism va raqamni kiriting:</b>\n\n<i>Masalan: HUSANOV 45</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buynow_print_no_"))
async def buynow_print_no(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    size = data.get("pending_size")
    from bot.handlers.cart import add_to_cart_direct
    await add_to_cart_direct(callback, product_id, size, state)
    await _go_to_checkout(callback, state)


async def _go_to_checkout(callback: CallbackQuery, state: FSMContext):
    """Savatga qo'shib darhol buyurtmaga o'tish"""
    from bot.handlers.order import OrderState
    from bot.keyboards.main_menu import cancel_kb
    await state.set_state(OrderState.waiting_address)
    await callback.message.answer(
        "⚡ <b>Tezkor buyurtma!</b>\n\n"
        "📍 Yetkazish manzilingizni yozing:\n"
        "<i>Masalan: Samarqand viloyati, Tayloq tumani, Musurmon</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
