from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal
from database.crud import get_product_by_id

router = Router()

# ─── In-memory cart ───────────────────────────────────────────────────────────
_carts: dict = {}

def get_cart(user_id: int) -> list:
    return _carts.get(user_id, [])

def set_cart(user_id: int, cart: list):
    _carts[user_id] = cart

def clear_cart(user_id: int):
    _carts[user_id] = []

def cart_total(cart: list) -> float:
    return sum(item["price"] * item["qty"] for item in cart)


# ─── FSM States ───────────────────────────────────────────────────────────────
class NameServiceState(StatesGroup):
    waiting_player_name = State()
    waiting_jersey_num  = State()

class PrintNameState(StatesGroup):
    waiting_name = State()   # Orqa ism yozish (forma uchun)


# ─── Cart formatter ───────────────────────────────────────────────────────────
def format_cart_text(cart: list) -> str:
    if not cart:
        return "🛒 <b>Savatingiz bo'sh</b>\n\nKatalogdan mahsulot tanlang 👇"
    lines = ["🛒 <b>Sizning savatingiz:</b>\n"]
    for i, item in enumerate(cart, 1):
        meta = []
        if item.get("size"):
            meta.append(f"O'lcham: <b>{item['size']}</b>")
        if item.get("player_name"):
            meta.append(f"Yoziladi: <b>{item['player_name']}</b>")
        if item.get("back_print"):
            meta.append(f"✍️ Orqa: <b>{item['back_print']}</b> (+50,000)")
        meta_str = (" | ".join(meta) + "\n   ") if meta else ""
        lines.append(
            f"{i}. {item['name']}\n"
            f"   {meta_str}"
            f"{int(item['price']):,} so'm × {item['qty']} = "
            f"<b>{int(item['price'] * item['qty']):,} so'm</b>"
        )
    lines.append(f"\n💰 <b>Jami: {int(cart_total(cart)):,} so'm</b>")
    return "\n".join(lines)


def cart_inline_kb(cart: list) -> InlineKeyboardMarkup:
    rows = []
    for i, item in enumerate(cart):
        label = item["name"][:20]
        if item.get("size"):
            label += f" ({item['size']})"
        rows.append([
            InlineKeyboardButton(text="❌", callback_data=f"cart_del_{i}"),
            InlineKeyboardButton(text=label, callback_data="noop"),
            InlineKeyboardButton(text="−", callback_data=f"cart_dec_{i}"),
            InlineKeyboardButton(text=str(item["qty"]), callback_data="noop"),
            InlineKeyboardButton(text="+", callback_data=f"cart_inc_{i}"),
        ])
    rows.append([InlineKeyboardButton(text="🗑 Savatni tozalash", callback_data="clear_cart")])
    rows.append([
        InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout"),
        InlineKeyboardButton(text="🛍 Katalog", callback_data="catalog"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛍 Katalogga o'tish", callback_data="catalog")
    ]])


# ─── Core add-to-cart ─────────────────────────────────────────────────────────
async def add_to_cart_direct(callback: CallbackQuery, product_id: int,
                              size, state: FSMContext, back_print: str = None):
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    cart = get_cart(user_id)
    is_name_service = (product.category_id == 4)

    if is_name_service:
        await state.set_state(NameServiceState.waiting_player_name)
        await state.update_data(
            ns_product_id=product_id,
            ns_name=product.name,
            ns_price=product.final_price
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        await callback.message.answer(
            "✍️ <b>Ism yozish xizmati</b>\n\n"
            "Futbolkaga yoziladigan <b>ism yoki laqab</b>ni kiriting:\n"
            "<i>Masalan: RONALDO, SARDOR, MESSI...</i>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Narxga orqa ism yozish qo'shimchasi
    price = product.final_price
    if back_print:
        price += 50000

    for item in cart:
        if item["product_id"] == product_id and item.get("size") == size:
            item["qty"] += 1
            set_cart(user_id, cart)
            await callback.answer(f"✅ {product.name} miqdori oshirildi!")
            return

    cart.append({
        "product_id": product_id,
        "name": product.name,
        "price": price,
        "qty": 1,
        "size": size,
        "player_name": None,
        "back_print": back_print,
        "needs_name": False,
    })
    set_cart(user_id, cart)
    size_text = f" ({size})" if size else ""
    print_text = f" | ✍️ {back_print}" if back_print else ""
    await callback.answer(f"✅ {product.name}{size_text}{print_text} savatga qo'shildi!")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass


# ─── FSM: Orqa ism yozish (PrintNameState) ────────────────────────────────────
@router.message(PrintNameState.waiting_name)
async def handle_print_name(message: Message, state: FSMContext):
    data = await state.get_data()
    name_input = message.text.strip().upper()

    if len(name_input) < 2 or len(name_input) > 25:
        await message.answer("⚠️ 2-25 ta belgi kiriting. Masalan: HUSANOV 45")
        return

    product_id = data["print_product_id"]
    size       = data.get("print_size")
    mode       = data.get("print_mode", "cart")  # cart yoki buynow

    async with AsyncSessionLocal() as session:
        product = await get_product_by_id(session, product_id)

    user_id = message.from_user.id
    cart = get_cart(user_id)
    price = product.final_price + 50000  # +50,000 so'm

    cart.append({
        "product_id": product_id,
        "name": product.name,
        "price": price,
        "qty": 1,
        "size": size,
        "player_name": None,
        "back_print": name_input,
        "needs_name": False,
    })
    set_cart(user_id, cart)

    await message.answer(
        f"✅ <b>Savatga qo'shildi!</b>\n\n"
        f"👕 {product.name}"
        f"{f' ({size})' if size else ''}\n"
        f"✍️ Orqa: <b>{name_input}</b>\n"
        f"💰 {int(price):,} so'm (ism yozish +50,000 so'm kiritilgan)\n\n"
        f"🛒 <b>Savatim</b> tugmasini bosing.",
        parse_mode="HTML"
    )

    # buy_now rejimida — darhol buyurtmaga o'tish
    if mode == "buynow":
        from bot.handlers.order import OrderState
        from bot.keyboards.main_menu import cancel_kb
        await state.set_state(OrderState.waiting_address)
        await message.answer(
            "⚡ <b>Tezkor buyurtma!</b>\n\n"
            "📍 Yetkazish manzilingizni yozing:\n"
            "<i>Masalan: Samarqand viloyati, Tayloq tumani</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )
    else:
        await state.clear()


# ─── FSM: Ism yozish xizmati ──────────────────────────────────────────────────
@router.message(NameServiceState.waiting_player_name)
async def handle_player_name(message: Message, state: FSMContext):
    name_input = message.text.strip().upper()
    if len(name_input) < 2 or len(name_input) > 20:
        await message.answer("⚠️ Ism 2-20 ta belgi bo'lishi kerak. Qaytadan kiriting:")
        return
    await state.update_data(ns_player_name=name_input)
    await state.set_state(NameServiceState.waiting_jersey_num)
    await message.answer(
        f"✅ Ism: <b>{name_input}</b>\n\n"
        "🔢 Forma <b>raqamini</b> kiriting (1-99):\n"
        "<i>Raqam kerak bo'lmasa — (tire) yuboring</i>",
        parse_mode="HTML"
    )


@router.message(NameServiceState.waiting_jersey_num)
async def handle_jersey_number(message: Message, state: FSMContext):
    data = await state.get_data()
    player_name = data["ns_player_name"]
    product_id  = data["ns_product_id"]
    prod_name   = data["ns_name"]
    price       = data["ns_price"]

    num_input = message.text.strip()
    if num_input == "-":
        full_label = player_name
    else:
        try:
            num = int(num_input)
            if not 1 <= num <= 99:
                await message.answer("⚠️ Raqam 1-99 oralig'ida (yoki — yuboring):")
                return
            full_label = f"{player_name} #{num}"
        except ValueError:
            await message.answer("⚠️ Faqat raqam yuboring yoki — yuboring:")
            return

    user_id = message.from_user.id
    cart = get_cart(user_id)
    cart.append({
        "product_id": product_id,
        "name": prod_name,
        "price": price,
        "qty": 1,
        "size": None,
        "player_name": full_label,
        "back_print": None,
        "needs_name": True,
    })
    set_cart(user_id, cart)
    await state.clear()

    await message.answer(
        f"🎉 <b>Savatga qo'shildi!</b>\n\n"
        f"✍️ {prod_name}\n"
        f"👕 Yoziladi: <b>{full_label}</b>\n"
        f"💰 {int(price):,} so'm\n\n"
        f"🛒 <b>Savatim</b> tugmasini bosing.",
        parse_mode="HTML"
    )


# ─── Show cart ────────────────────────────────────────────────────────────────
@router.message(F.text == "🛒 Savatim")
async def show_cart(message: Message):
    cart = get_cart(message.from_user.id)
    text = format_cart_text(cart)
    kb = cart_inline_kb(cart) if cart else empty_cart_kb()
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def _refresh_cart_message(callback: CallbackQuery):
    cart = get_cart(callback.from_user.id)
    text = format_cart_text(cart)
    kb = cart_inline_kb(cart) if cart else empty_cart_kb()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except:
        pass


# ─── Cart controls ────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("cart_inc_"))
async def cart_increment(callback: CallbackQuery):
    idx = int(callback.data.split("_")[2])
    cart = get_cart(callback.from_user.id)
    if 0 <= idx < len(cart):
        cart[idx]["qty"] += 1
        set_cart(callback.from_user.id, cart)
    await _refresh_cart_message(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_dec_"))
async def cart_decrement(callback: CallbackQuery):
    idx = int(callback.data.split("_")[2])
    cart = get_cart(callback.from_user.id)
    if 0 <= idx < len(cart):
        if cart[idx]["qty"] > 1:
            cart[idx]["qty"] -= 1
        else:
            cart.pop(idx)
        set_cart(callback.from_user.id, cart)
    await _refresh_cart_message(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("cart_del_"))
async def cart_delete_item(callback: CallbackQuery):
    idx = int(callback.data.split("_")[2])
    cart = get_cart(callback.from_user.id)
    if 0 <= idx < len(cart):
        removed = cart.pop(idx)
        set_cart(callback.from_user.id, cart)
        await callback.answer(f"🗑 {removed['name']} o'chirildi")
    else:
        await callback.answer()
    await _refresh_cart_message(callback)


@router.callback_query(F.data == "clear_cart")
async def clear_cart_callback(callback: CallbackQuery):
    clear_cart(callback.from_user.id)
    await callback.answer("✅ Savat tozalandi")
    await _refresh_cart_message(callback)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery, state: FSMContext):
    cart = get_cart(callback.from_user.id)
    if not cart:
        await callback.answer("Savat bo'sh!", show_alert=True)
        return
    from bot.handlers.order import OrderState
    from bot.keyboards.main_menu import cancel_kb
    await state.set_state(OrderState.waiting_address)
    await callback.message.answer(
        "📍 <b>Yetkazish manzilingizni yozing:</b>\n\n"
        "<i>Masalan: Samarqand viloyati, Tayloq tumani, Musurmon</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()
