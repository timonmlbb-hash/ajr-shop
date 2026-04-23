from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.db import AsyncSessionLocal
from database.crud import (
    get_all_categories, get_category_by_id,
    get_products_by_category, get_product_by_id,
    get_product_stocks
)

router = Router()

# Forma kategoriyalari (ism yozish taklifi uchun)
FORMA_CATEGORIES = [1, 2]


def format_price(product) -> str:
    if product.discount_percent > 0:
        old = f"{int(product.price):,}"
        new = f"{int(product.final_price):,}"
        return f"<s>{old}</s> → <b>{new} so'm</b> 🔥 -{int(product.discount_percent)}%"
    return f"<b>{int(product.price):,} so'm</b>"


# ─── Keyboards ────────────────────────────────────────────────────────────────
def categories_kb(categories) -> InlineKeyboardMarkup:
    rows = []
    for cat in categories:
        if cat.id == 4:  # Ism yozish — katalogda ko'rinmaydi
            continue
        rows.append([InlineKeyboardButton(
            text=f"{cat.emoji} {cat.name}",
            callback_data=f"cat_{cat.id}"
        )])
    rows.append([InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_kb(products, category_id: int) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        price_str = f"{int(p.final_price):,} so'm"
        if p.discount_percent > 0:
            price_str += f" (-{int(p.discount_percent)}%)"
        # Ombor holati
        total_qty = sum(s.quantity for s in p.stocks) if p.stocks else 0
        if total_qty == 0:
            stock_icon = " ❌"
        elif total_qty <= 3:
            stock_icon = " ⚠️"
        else:
            stock_icon = ""
        rows.append([InlineKeyboardButton(
            text=f"{p.name}{stock_icon} — {price_str}",
            callback_data=f"prod_{p.id}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_detail_kb(product) -> InlineKeyboardMarkup:
    """Savatga + Tezkor buyurtma tugmalari"""
    rows = []
    if product.in_stock:
        rows.append([
            InlineKeyboardButton(text="🛒 Savatga", callback_data=f"add_cart_{product.id}"),
            InlineKeyboardButton(text="⚡ Tezkor buyurtma", callback_data=f"buy_now_{product.id}"),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{product.category_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def size_kb_with_stock(stocks: list, product_id: int,
                        buy_now: bool = False) -> InlineKeyboardMarkup:
    """
    O'lchamlar + stock holati.
    - ✅ 5 ta  → bosiladi
    - ⚠️ 2 ta  → bosiladi (kam qoldi)
    - ❌ tugadi → bosilmaydi (noop)
    Faqat admin kiritgan o'lchamlar ko'rinadi!
    """
    prefix = "buynow_size" if buy_now else "size"
    rows = []
    row = []
    for stock in sorted(stocks, key=lambda s: s.sort_order):
        if stock.status == "out":
            # Tugagan — bosilmaydi
            btn = InlineKeyboardButton(
                text=f"{stock.size} ❌",
                callback_data="stock_out"
            )
        elif stock.status == "low":
            btn = InlineKeyboardButton(
                text=f"{stock.size} ⚠️{stock.quantity}",
                callback_data=f"{prefix}_{product_id}_{stock.size}"
            )
        else:
            btn = InlineKeyboardButton(
                text=f"{stock.size} ✅",
                callback_data=f"{prefix}_{product_id}_{stock.size}"
            )
        row.append(btn)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Bekor", callback_data=f"cat_{product_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_print_kb(product_id: int, buy_now: bool = False) -> InlineKeyboardMarkup:
    prefix = "buynow" if buy_now else "cart"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Ha (+50,000 so'm)",
                callback_data=f"{prefix}_print_yes_{product_id}"
            ),
            InlineKeyboardButton(
                text="❌ Yo'q",
                callback_data=f"{prefix}_print_no_{product_id}"
            ),
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
        products  = await get_products_by_category(session, category_id)
        # Har bir mahsulot uchun stocklarni yuklash
        for p in products:
            p.stocks = await get_product_stocks(session, p.id)

    if not products:
        await callback.answer("😕 Bu kategoriyada hozircha mahsulot yo'q", show_alert=True)
        return

    text = f"{category.emoji} <b>{category.name}</b>\n"
    if category.description:
        text += f"\n📝 {category.description}\n"
    text += f"\n📦 {len(products)} ta mahsulot\n\nTanlang 👇"

    try:
        await callback.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=products_kb(products, category_id)
        )
    except:
        await callback.message.answer(
            text, parse_mode="HTML",
            reply_markup=products_kb(products, category_id)
        )


@router.callback_query(F.data.startswith("prod_"))
async def show_product_detail(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)
        stocks  = await get_product_stocks(session, product_id)

    if not product:
        await callback.answer("Mahsulot topilmadi", show_alert=True)
        return

    # Ombor holati matni
    stock_text = ""
    if stocks:
        available = [s for s in stocks if s.quantity > 0]
        if not available:
            stock_text = "\n⛔ <b>Hamma o'lchamlar tugagan</b>"
        else:
            sizes_info = []
            for s in sorted(stocks, key=lambda x: x.sort_order):
                if s.status == "out":
                    sizes_info.append(f"{s.size}❌")
                elif s.status == "low":
                    sizes_info.append(f"{s.size}⚠️")
                else:
                    sizes_info.append(f"{s.size}✅")
            stock_text = "\n📦 O'lchamlar: " + "  ".join(sizes_info)

    text = f"<b>{product.name}</b>\n\n"
    if product.description:
        text += f"📝 {product.description}\n\n"
    text += f"💰 Narxi: {format_price(product)}"
    text += stock_text

    if product.category_id in FORMA_CATEGORIES:
        text += "\n\n✍️ <i>Forma orqasiga ism yozish: +50,000 so'm</i>"

    # Omborda bo'lsa ko'rsatish
    has_stock = any(s.quantity > 0 for s in stocks) if stocks else product.in_stock
    kb = product_detail_kb(product) if has_stock else InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{product.category_id}")
    ]])

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


@router.callback_query(F.data == "stock_out")
async def stock_out_click(callback: CallbackQuery):
    await callback.answer("❌ Bu o'lcham tugagan!", show_alert=True)


# ─── Savatga qo'shish ─────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("add_cart_"))
async def ask_size_or_add(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)
        stocks  = await get_product_stocks(session, product_id)

    if product.category_id == 4:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, None, state)
        return

    if not stocks:
        await callback.answer("😕 O'lchamlar kiritilmagan", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=size_kb_with_stock(stocks, product_id, buy_now=False)
        )
    except:
        await callback.message.answer(
            "📏 O'lchamni tanlang:",
            reply_markup=size_kb_with_stock(stocks, product_id, buy_now=False)
        )
    await callback.answer("📏 O'lchamni tanlang 👇")


@router.callback_query(F.data.startswith("size_"))
async def handle_size_cart(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    product_id = int(parts[1])
    size = parts[2]

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)
        stocks  = await get_product_stocks(session, product_id)

    # Stock tekshirish (tugab qolgan bo'lsa)
    stock_qty = next((s.quantity for s in stocks if s.size == size), 0)
    if stock_qty == 0:
        await callback.answer("❌ Bu o'lcham tugagan!", show_alert=True)
        return

    if product.category_id in FORMA_CATEGORIES:
        await state.update_data(pending_product_id=product_id, pending_size=size, pending_mode="cart")
        try:
            await callback.message.edit_reply_markup(
                reply_markup=back_print_kb(product_id, buy_now=False)
            )
        except:
            await callback.message.answer(
                f"✍️ Forma orqasiga <b>ism va raqam</b> yozdirasizmi?\n<i>+50,000 so'm</i>",
                parse_mode="HTML",
                reply_markup=back_print_kb(product_id, buy_now=False)
            )
        await callback.answer(f"✅ O'lcham: {size}")
    else:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, size, state)


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


# ─── Tezkor buyurtma ──────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("buy_now_"))
async def buy_now(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)
        stocks  = await get_product_stocks(session, product_id)

    if product.category_id == 4:
        from bot.handlers.cart import add_to_cart_direct
        await add_to_cart_direct(callback, product_id, None, state)
        await state.update_data(buy_now_after=True)
        return

    if not stocks:
        await callback.answer("😕 O'lchamlar kiritilmagan", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=size_kb_with_stock(stocks, product_id, buy_now=True)
        )
    except:
        await callback.message.answer(
            "📏 O'lchamni tanlang:",
            reply_markup=size_kb_with_stock(stocks, product_id, buy_now=True)
        )
    await callback.answer("📏 O'lchamni tanlang 👇")


@router.callback_query(F.data.startswith("buynow_size_"))
async def handle_size_buynow(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 3)
    product_id = int(parts[2])
    size = parts[3]

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)
        stocks  = await get_product_stocks(session, product_id)

    stock_qty = next((s.quantity for s in stocks if s.size == size), 0)
    if stock_qty == 0:
        await callback.answer("❌ Bu o'lcham tugagan!", show_alert=True)
        return

    if product.category_id in FORMA_CATEGORIES:
        await state.update_data(pending_product_id=product_id, pending_size=size, pending_mode="buynow")
        try:
            await callback.message.edit_reply_markup(
                reply_markup=back_print_kb(product_id, buy_now=True)
            )
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
    from bot.handlers.order import OrderState
    from bot.keyboards.main_menu import cancel_kb
    await state.set_state(OrderState.waiting_name)
    await callback.message.answer(
        "⚡ <b>Tezkor buyurtma!</b>\n\n"
        "👤 Ismingizni kiriting:\n"
        "<i>Masalan: Musurmon Husanov</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
