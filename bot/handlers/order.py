import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal
from database.crud import (
    get_user_by_telegram_id, get_product_by_id,
    create_order, add_order_item,
    update_order_total, get_order_with_items, update_order_status
)
from bot.handlers.cart import get_cart, clear_cart
from bot.keyboards.main_menu import main_menu_kb, payment_kb, cancel_kb
from bot.keyboards.admin_kb import order_actions_kb
from bot.middlewares.admin_check import is_admin, ADMIN_IDS, GROUP_CHAT_ID

router = Router()

PAYNET_LINK = (
    "https://app.paynet.uz/qr-online/00020101021140440012qr-online.uz"
    "01186r0C2GWSuXEb8UE7KQ0202115204531153038605802UZ5910AO'PAYNET'"
    "6008Tashkent610610002164280002uz0106PAYNET0208Toshkent80520012"
    "qr-online.uz03097120207070419marketing@paynet.uz6304A3D2"
)

SHOP_ADDRESS = (
    "📍 <b>Do'kon manzili:</b>\n"
    "Uchtepa outlet center B157 do'kon\n"
    "⏱️ Ish vaqti: 11:00 - 22:00\n\n"
    "📞 Kelishdan oldin qo'ng'iroq qiling!"
)

PAYMENT_MAP = {
    "💳 Karta / Paynet":             "card",
    "🤝 Uzum Nasiya":                "credit",
    "🚶 O'zim borib olaman":          "cash",
}
PAYMENT_EMOJI = {
    "card":   "💳 Karta / Paynet",
    "credit": "🤝 Uzum Nasiya",
    "cash":   "🚶 Borib olish",
}
STATUS_TEXT = {
    "pending":    "⏳ Kutilmoqda",
    "confirmed":  "✅ Tasdiqlangan",
    "delivering": "📦 Pochtaga topshirildi",
    "done":       "✔️ Yakunlandi",
    "cancelled":  "❌ Bekor qilindi",
}


class OrderState(StatesGroup):
    waiting_name    = State()   # Mijoz ismi
    waiting_phone   = State()   # Telefon raqam
    waiting_address = State()   # Viloyat, tuman, manzil
    waiting_payment = State()   # To'lov usuli


# ─── Cancel ───────────────────────────────────────────────────────────────────
@router.message(F.text == "❌ Bekor qilish")
async def cancel_order_flow(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("❌ Bekor qilindi.", reply_markup=main_menu_kb(is_admin=admin))


# ─── Step 1: Ism ─────────────────────────────────────────────────────────────
@router.message(OrderState.waiting_name)
async def handle_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("⚠️ Ism juda qisqa. To'liq ismingizni kiriting:")
        return
    await state.update_data(customer_name=name)
    await state.set_state(OrderState.waiting_phone)
    await message.answer(
        f"👤 Ism: <b>{name}</b>\n\n"
        "📱 <b>Telefon raqamingizni yozing:</b>\n"
        "<i>Masalan: +998 93 107 13 08</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


# ─── Step 2: Telefon ──────────────────────────────────────────────────────────
@router.message(OrderState.waiting_phone)
async def handle_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    # Kontakt yuborilsa
    if message.contact:
        phone = message.contact.phone_number
    if len(phone) < 7:
        await message.answer("⚠️ Telefon raqam noto'g'ri. Qaytadan kiriting:")
        return
    await state.update_data(customer_phone=phone)
    await state.set_state(OrderState.waiting_address)
    await message.answer(
        f"📱 Telefon: <b>{phone}</b>\n\n"
        "📍 <b>Yetkazish manzilingizni yozing:</b>\n"
        "<i>Viloyat, tuman va aniq manzilni kiriting\n"
        "Masalan: Samarqand viloyati, Tayloq tumani, Musurmon qishlog'i</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


# ─── Step 3: Manzil ───────────────────────────────────────────────────────────
@router.message(OrderState.waiting_address)
async def handle_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 10:
        await message.answer(
            "⚠️ Manzil juda qisqa. Viloyat va tumanni ham yozing:\n"
            "<i>Masalan: Samarqand viloyati, Tayloq tumani, Musurmon</i>",
            parse_mode="HTML"
        )
        return
    await state.update_data(address=address)
    await state.set_state(OrderState.waiting_payment)
    await message.answer(
        f"📍 Manzil: <b>{address}</b>\n\n"
        "💳 <b>To'lov usulini tanlang:</b>\n\n"
        "💳 <b>Karta / Paynet</b> — to'lov linki yuboriladi\n"
        "🤝 <b>Uzum Nasiya</b> — admin bilan bog'laniladi\n"
        "🚶 <b>Borib olish</b> — Toshkent, do'kondan o'zingiz olasiz\n\n"
        "📦 <i>Viloyatlarga BTS pochta orqali: 20,000 - 30,000 so'm</i>",
        parse_mode="HTML",
        reply_markup=payment_kb()
    )


# ─── Step 4: To'lov ───────────────────────────────────────────────────────────
@router.message(OrderState.waiting_payment)
async def handle_payment(message: Message, state: FSMContext, bot: Bot):
    payment_text = message.text
    if payment_text not in PAYMENT_MAP:
        await message.answer("⚠️ Iltimos, tugmalardan birini bosing.")
        return

    payment_type = PAYMENT_MAP[payment_text]
    data         = await state.get_data()
    customer_name  = data.get("customer_name", message.from_user.full_name)
    customer_phone = data.get("customer_phone", "—")
    address        = data["address"]
    cart           = get_cart(message.from_user.id)
    admin          = is_admin(message.from_user.id)

    if not cart:
        await state.clear()
        await message.answer("❌ Savat bo'sh!", reply_markup=main_menu_kb(is_admin=admin))
        return

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Xato! /start bosing.")
            return

        order = await create_order(
            session,
            user_id=user.id,
            payment_type=payment_type,
            delivery_address=address,
            comment=f"Ism: {customer_name} | Tel: {customer_phone}"
        )

        total = 0
        for item in cart:
            await add_order_item(
                session,
                order_id=order.id,
                product_id=item["product_id"],
                quantity=item["qty"],
                price=item["price"],
                size=item.get("size"),
                player_name=item.get("back_print") or item.get("player_name")
            )
            total += item["price"] * item["qty"]

        await update_order_total(session, order.id, total)

    clear_cart(message.from_user.id)
    await state.clear()

    # ─── Mahsulotlar matni ────────────────────────────────────────────────────
    cart_lines = ""
    for item in cart:
        extra = ""
        if item.get("size"):        extra += f" ({item['size']})"
        if item.get("back_print"):  extra += f" | ✍️ {item['back_print']}"
        if item.get("player_name"): extra += f" | ✍️ {item['player_name']}"
        cart_lines += f"• {item['name']}{extra} × {item['qty']} = {int(item['price'] * item['qty']):,} so'm\n"

    payment_label = PAYMENT_EMOJI.get(payment_type, payment_text)

    base_text = (
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n"
        f"{'─' * 28}\n"
        f"🔢 Buyurtma: <b>#{order.id}</b>\n"
        f"👤 {customer_name} | 📱 {customer_phone}\n"
        f"📍 {address}\n"
        f"💳 {payment_label}\n"
        f"{'─' * 28}\n"
        f"{cart_lines}"
        f"{'─' * 28}\n"
        f"💰 <b>Jami: {int(total):,} so'm</b>\n"
        f"{'─' * 28}\n"
    )

    # ─── Mijozga xabar ────────────────────────────────────────────────────────
    await message.answer("✅", reply_markup=main_menu_kb(is_admin=admin))

    if payment_type == "card":
        await message.answer(
            base_text + "💳 <b>Karta / Paynet orqali to'lang:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💳 Paynet orqali to'lash", url=PAYNET_LINK)
            ]])
        )
    elif payment_type == "credit":
        await message.answer(
            base_text + "🤝 <b>Uzum Nasiya</b>\n\nAdmin siz bilan tez orada bog'lanadi 📞",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            base_text + "🚶 <b>Borib olish</b>\n\n" + SHOP_ADDRESS,
            parse_mode="HTML"
        )

    # ─── Guruh chatga + Adminga xabar ────────────────────────────────────────
    nasiya_note = "\n⚠️ <b>UZUM NASIYA — ko'rib chiqing!</b>" if payment_type == "credit" else ""

    admin_text = (
        f"🆕 <b>YANGI BUYURTMA #{order.id}</b>{nasiya_note}\n"
        f"{'─' * 28}\n"
        f"👤 {customer_name}"
        f"{'  @' + message.from_user.username if message.from_user.username else ''}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"📱 {customer_phone}\n"
        f"{'─' * 28}\n"
        f"📍 {address}\n"
        f"💳 {payment_label}\n"
        f"{'─' * 28}\n"
        f"{cart_lines}"
        f"{'─' * 28}\n"
        f"💰 <b>JAMI: {int(total):,} so'm</b>"
    )

    # Yuborish manzillari: guruh + individual adminlar
    targets = list(set([GROUP_CHAT_ID] + ADMIN_IDS))

    for target_id in targets:
        try:
            # Har bir mahsulot rasmi bilan
            for item in cart:
                async with AsyncSessionLocal() as session:
                    product = await get_product_by_id(session, item["product_id"])
                if product and product.photo_url:
                    s = f" ({item['size']})" if item.get("size") else ""
                    b = f" | ✍️ {item['back_print']}" if item.get("back_print") else ""
                    p = f" | ✍️ {item['player_name']}" if item.get("player_name") else ""
                    cap = f"🖼 <b>{product.name}</b>{s}{b}{p}\n💰 {int(item['price']):,} so'm × {item['qty']}"
                    await bot.send_photo(
                        target_id,
                        photo=product.photo_url,
                        caption=cap,
                        parse_mode="HTML"
                    )

            await bot.send_message(
                target_id, admin_text,
                parse_mode="HTML",
                reply_markup=order_actions_kb(order.id)
            )
        except Exception as e:
            print(f"Target {target_id}ga xabar yuborishda xato: {e}")


# ─── My orders ────────────────────────────────────────────────────────────────
@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(message: Message):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from database.models import Order

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Hali buyurtma yo'q.")
            return
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(10)
        )
        orders = result.scalars().all()

    if not orders:
        await message.answer("📦 Hali buyurtma yo'q.\n\n🛍 Katalogdan xarid qiling!")
        return

    text = "📦 <b>Sizning buyurtmalaringiz:</b>\n\n"
    for order in orders:
        status  = STATUS_TEXT.get(order.status.value, order.status.value)
        payment = PAYMENT_EMOJI.get(order.payment_type.value if order.payment_type else "", "")
        text += (
            f"🔢 <b>#{order.id}</b>  {status}\n"
            f"💰 {int(order.total_price):,} so'm  {payment}\n"
            f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        )
    await message.answer(text, parse_mode="HTML")


# ─── Admin status actions ─────────────────────────────────────────────────────
async def _status_update(callback: CallbackQuery, bot: Bot, order_id: int, new_status: str):
    async with AsyncSessionLocal() as session:
        await update_order_status(session, order_id, new_status)
        order = await get_order_with_items(session, order_id)

    status_label = STATUS_TEXT.get(new_status, new_status)
    who = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n📌 <b>{status_label}</b>  ✅ {who}",
            parse_mode="HTML"
        )
    except:
        pass
    await callback.answer(f"✅ {status_label}")

    if not (order and order.user):
        return

    # ─── Mijozga status xabarlari ─────────────────────────────────────────────
    if new_status == "confirmed":
        msg = "✅ <b>Buyurtmangiz tasdiqlandi!</b>\n\nTez orada jo'natiladi 📦"
        # Nasiya → Paynet linki
        if order.payment_type and order.payment_type.value == "credit":
            msg += f"\n\n💰 To'lov summasi: <b>{int(order.total_price):,} so'm</b>\n👇 To'lov uchun:"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💳 Paynet orqali to'lash", url=PAYNET_LINK)
            ]])
        # Borib olish → do'kon manzili
        elif order.payment_type and order.payment_type.value == "cash":
            msg += "\n\n" + SHOP_ADDRESS
            kb = None
        else:
            kb = None

    elif new_status == "delivering":
        msg = (
            "📦 <b>Buyurtmangiz BTS pochtaga topshirildi!</b>\n\n"
            "📬 1-3 ish kuni ichida qo'lingizda bo'ladi.\n"
            "Trek raqam tayyor bo'lgach yuboriladi."
        )
        kb = None
        # 2 kundan keyin sharh so'rash (production da asyncio.sleep ishlatmang, scheduler yaxshiroq)
        # Hozircha darhol so'raymiz
        try:
            from bot.handlers.review import ask_review
            await ask_review(bot, order.user.telegram_id, order_id)
        except Exception as e:
            print(f"Review so'rovda xato: {e}")

    elif new_status == "cancelled":
        msg = "❌ <b>Buyurtmangiz bekor qilindi.</b>\n\nSavollar uchun @formachi_admin ga yozing."
        kb = None
    else:
        return

    try:
        await bot.send_message(
            order.user.telegram_id,
            f"📦 <b>Buyurtma #{order_id}</b>\n\n{msg}",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception as e:
        print(f"Mijozga xabar yuborishda xato: {e}")


@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "confirmed")

@router.callback_query(F.data.startswith("admin_deliver_"))
async def admin_deliver(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "delivering")

@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_cancel(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "cancelled")
