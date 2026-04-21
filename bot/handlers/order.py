import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal
from database.crud import (
    get_user_by_telegram_id, create_order, add_order_item,
    update_order_total, get_order_with_items, update_order_status
)
from bot.handlers.cart import get_cart, clear_cart, cart_total
from bot.keyboards.main_menu import main_menu_kb, payment_kb, cancel_kb
from bot.keyboards.admin_kb import order_actions_kb
from bot.middlewares.admin_check import is_admin, ADMIN_IDS

router = Router()

PAYMENT_MAP = {
    "💵 Naqd": "cash",
    "💳 Karta": "card",
    "🤝 Nasiya": "credit",
}
PAYMENT_EMOJI = {
    "cash": "💵 Naqd",
    "card": "💳 Karta",
    "credit": "🤝 Nasiya",
}
STATUS_TEXT = {
    "pending":    "⏳ Kutilmoqda",
    "confirmed":  "✅ Tasdiqlangan",
    "delivering": "🚚 Yetkazilmoqda",
    "done":       "✔️ Yetkazildi",
    "cancelled":  "❌ Bekor qilindi",
}


class OrderState(StatesGroup):
    waiting_address = State()
    waiting_comment = State()
    waiting_payment = State()


# ─── Cancel ───────────────────────────────────────────────────────────────────
@router.message(F.text == "❌ Bekor qilish")
async def cancel_order_flow(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("❌ Bekor qilindi.", reply_markup=main_menu_kb(is_admin=admin))


# ─── Step 1: Manzil ───────────────────────────────────────────────────────────
@router.message(OrderState.waiting_address)
async def handle_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 10:
        await message.answer(
            "⚠️ Manzil juda qisqa. To'liqroq yozing:\n"
            "<i>Masalan: Toshkent, Chilonzor tumani, 19-mavze, 5-uy</i>",
            parse_mode="HTML"
        )
        return
    await state.update_data(address=address)
    await state.set_state(OrderState.waiting_comment)
    await message.answer(
        f"📍 Manzil saqlandi: <b>{address}</b>\n\n"
        "💬 Qo'shimcha izoh yozing (o'lcham, rang, maxsus xohish...):\n"
        "<i>Izoh kerak bo'lmasa — yuboring</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


# ─── Step 2: Izoh ────────────────────────────────────────────────────────────
@router.message(OrderState.waiting_comment)
async def handle_comment(message: Message, state: FSMContext):
    comment = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(comment=comment)
    await state.set_state(OrderState.waiting_payment)
    await message.answer(
        "💳 <b>To'lov usulini tanlang:</b>",
        parse_mode="HTML",
        reply_markup=payment_kb()
    )


# ─── Step 3: To'lov + Buyurtma yaratish ──────────────────────────────────────
@router.message(OrderState.waiting_payment)
async def handle_payment(message: Message, state: FSMContext, bot: Bot):
    payment_text = message.text
    if payment_text not in PAYMENT_MAP:
        await message.answer("⚠️ Iltimos, tugmalardan birini bosing.")
        return

    payment_type = PAYMENT_MAP[payment_text]
    data = await state.get_data()
    address = data["address"]
    comment = data.get("comment")
    cart    = get_cart(message.from_user.id)
    admin   = is_admin(message.from_user.id)

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
            comment=comment
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
                player_name=item.get("player_name")
            )
            total += item["price"] * item["qty"]

        await update_order_total(session, order.id, total)

    clear_cart(message.from_user.id)
    await state.clear()

    # ─── Mijozga tasdiqlash xabari ───────────────────────────────────────────
    cart_lines = ""
    for item in cart:
        extra = ""
        if item.get("size"):
            extra += f" | {item['size']}"
        if item.get("player_name"):
            extra += f" | ✍️{item['player_name']}"
        cart_lines += f"• {item['name']}{extra} × {item['qty']} = {int(item['price'] * item['qty']):,} so'm\n"

    await message.answer(
        f"🎉 <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"🔢 Buyurtma: <b>#{order.id}</b>\n"
        f"📍 Manzil: {address}\n"
        f"💳 To'lov: {payment_text}\n"
        f"{'💬 Izoh: ' + comment + chr(10) if comment else ''}"
        f"\n{cart_lines}\n"
        f"💰 <b>Jami: {int(total):,} so'm</b>\n\n"
        f"⏳ Admin tasdiqlashini kuting.\n"
        f"Tez orada siz bilan bog'lanamiz! 📞",
        parse_mode="HTML",
        reply_markup=main_menu_kb(is_admin=admin)
    )

    # ─── Adminga xabar ───────────────────────────────────────────────────────
    admin_text = (
        f"🆕 <b>YANGI BUYURTMA #{order.id}</b>\n"
        f"{'─' * 28}\n"
        f"👤 {message.from_user.full_name}"
        f"{'  @' + message.from_user.username if message.from_user.username else ''}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"📱 {user.phone or '—'}\n"
        f"{'─' * 28}\n"
        f"📍 {address}\n"
        f"💳 {payment_text}\n"
        f"{'💬 ' + comment + chr(10) if comment else ''}"
        f"{'─' * 28}\n"
    )
    for item in cart:
        extra = ""
        if item.get("size"):   extra += f" ({item['size']})"
        if item.get("player_name"): extra += f" ✍️{item['player_name']}"
        admin_text += f"• {item['name']}{extra} × {item['qty']} = {int(item['price'] * item['qty']):,} so'm\n"
    admin_text += f"{'─' * 28}\n💰 <b>JAMI: {int(total):,} so'm</b>"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, admin_text,
                parse_mode="HTML",
                reply_markup=order_actions_kb(order.id)
            )
        except Exception as e:
            print(f"Admin {admin_id}ga xabar yuborishda xato: {e}")


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


# ─── Admin order status actions ───────────────────────────────────────────────
NOTIFY_MESSAGES = {
    "confirmed":  "✅ <b>Buyurtmangiz tasdiqlandi!</b>\n\nTez orada qo'lingizda bo'ladi 🎉⚽",
    "delivering": "🚚 <b>Buyurtmangiz yo'lga chiqdi!</b>\n\nKuryer tez orada yetib boradi.",
    "done":       "🏆 <b>Buyurtmangiz yetkazildi!</b>\n\nRahmat! Keyingi xaridda ham kutamiz ⚽",
    "cancelled":  "❌ <b>Buyurtmangiz bekor qilindi.</b>\n\nSavollar uchun admin bilan bog'laning.",
}


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

    if order and order.user:
        msg = NOTIFY_MESSAGES.get(new_status, "")
        if msg:
            try:
                await bot.send_message(
                    order.user.telegram_id,
                    f"📦 <b>Buyurtma #{order_id}</b>\n\n{msg}",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Mijozga xabar yuborishda xato: {e}")


@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "confirmed")


@router.callback_query(F.data.startswith("admin_deliver_"))
async def admin_deliver(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "delivering")


@router.callback_query(F.data.startswith("admin_done_"))
async def admin_done(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "done")


@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_cancel(callback: CallbackQuery, bot: Bot):
    await _status_update(callback, bot, int(callback.data.split("_")[2]), "cancelled")
