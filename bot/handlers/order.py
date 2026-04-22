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
from bot.middlewares.admin_check import is_admin, ADMIN_IDS

router = Router()

PAYNET_LINK = "https://app.paynet.uz/qr-online/00020101021140440012qr-online.uz01186r0C2GWSuXEb8UE7KQ0202115204531153038605802UZ5910AO'PAYNET'6008Tashkent610610002164280002uz0106PAYNET0208Toshkent80520012qr-online.uz03097120207070419marketing@paynet.uz6304A3D2"

# Do'kon manzili
SHOP_ADDRESS = (
    "📍 <b>Do'kon manzili:</b>\n"
    "Uchtepa outlet center B157 do'kon\n"
    "⏱️ Ish vaqti: 11:00 - 22:00\n\n"
    "📞 Kelishdan oldin qo'ng'iroq qiling!"
)

PAYMENT_MAP = {
    "💳 Karta / Paynet":            "card",
    "🤝 Nasiya (Admin tasdiqlaydi)": "credit",
    "🚶 O'zim borib olaman":          "cash",
}
PAYMENT_EMOJI = {
    "card":   "💳 Karta / Paynet",
    "credit": "🤝 Nasiya",
    "cash":   "🚶 Borib olish",
}
STATUS_TEXT = {
    "pending":    "⏳ Kutilmoqda",
    "confirmed":  "✅ Tasdiqlangan",
    "delivering": "🚚 Yetkazilmoqda",
    "done":       "✔️ Yetkazildi",
    "cancelled":  "❌ Bekor qilindi",
}
NOTIFY_MESSAGES = {
    "confirmed":  "✅ <b>Buyurtmangiz tasdiqlandi!</b>\n\nTez orada qo'lingizda bo'ladi 🎉",
    "delivering": "🚚 <b>Buyurtmangiz yo'lga chiqdi!</b>\n\nBTS pochta orqali yuborildi. 3-5 kun ichida yetib boradi.",
    "done":       "🏆 <b>Buyurtmangiz yetkazildi!</b>\n\nXaridingiz uchun rahmat! ⚽",
    "cancelled":  "❌ <b>Buyurtmangiz bekor qilindi.</b>\n\nSavollar uchun @formachi_admin ga yozing.",
}


class OrderState(StatesGroup):
    waiting_address = State()
    waiting_comment = State()
    waiting_payment = State()


@router.message(F.text == "❌ Bekor qilish")
async def cancel_order_flow(message: Message, state: FSMContext):
    await state.clear()
    admin = is_admin(message.from_user.id)
    await message.answer("❌ Bekor qilindi.", reply_markup=main_menu_kb(is_admin=admin))


@router.message(OrderState.waiting_address)
async def handle_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 5:
        await message.answer(
            "⚠️ Manzil juda qisqa:\n"
            "<i>Masalan: Samarqand viloyati, Tayloq tumani, Musurmon</i>",
            parse_mode="HTML"
        )
        return
    await state.update_data(address=address)
    await state.set_state(OrderState.waiting_comment)
    await message.answer(
        f"📍 Manzil: <b>{address}</b>\n\n"
        "💬 Telefon raqamingizni yozing yoki qo'shimcha izoh:\n"
        "<i>(Kerak bo'lmasa — yuboring)</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )


@router.message(OrderState.waiting_comment)
async def handle_comment(message: Message, state: FSMContext):
    comment = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(comment=comment)
    await state.set_state(OrderState.waiting_payment)
    await message.answer(
        "💳 <b>To'lov usulini tanlang:</b>\n\n"
        "💳 <b>Karta / Paynet</b> — to'lov linki yuboriladi\n"
        "🤝 <b>Nasiya</b> — admin ko'rib chiqadi\n"
        "🚶 <b>Borib olish</b> — do'kondan o'zingiz olasiz\n\n"
        "📦 <i>BTS pochta orqali yetkazish: 20,000 - 30,000 so'm</i>",
        parse_mode="HTML",
        reply_markup=payment_kb()
    )


@router.message(OrderState.waiting_payment)
async def handle_payment(message: Message, state: FSMContext, bot: Bot):
    payment_text = message.text
    if payment_text not in PAYMENT_MAP:
        await message.answer("⚠️ Iltimos, tugmalardan birini bosing.")
        return

    payment_type = PAYMENT_MAP[payment_text]
    data = await state.get_data()
    address  = data["address"]
    comment  = data.get("comment")
    cart     = get_cart(message.from_user.id)
    admin    = is_admin(message.from_user.id)

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
        if item.get("size"):        extra += f" | {item['size']}"
        if item.get("back_print"):  extra += f" | ✍️ {item['back_print']}"
        if item.get("player_name"): extra += f" | ✍️ {item['player_name']}"
        cart_lines += f"• {item['name']}{extra} × {item['qty']} = {int(item['price'] * item['qty']):,} so'm\n"

    base_text = (
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n"
        f"{'─' * 28}\n"
        f"🔢 Buyurtma: <b>#{order.id}</b>\n"
        f"📍 Manzil: {address}\n"
        f"{'💬 ' + comment + chr(10) if comment else ''}"
        f"{'─' * 28}\n"
        f"{cart_lines}"
        f"{'─' * 28}\n"
        f"💰 <b>Jami: {int(total):,} so'm</b>\n"
        f"{'─' * 28}\n"
    )

    await message.answer(main_menu_kb(is_admin=admin), reply_markup=main_menu_kb(is_admin=admin))

    if payment_type == "card":
        await message.answer(
            base_text + "💳 <b>To'lov: Karta / Paynet</b>\n\nQuyidagi tugma orqali to'lovni amalga oshiring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💳 Paynet orqali to'lash", url=PAYNET_LINK)
            ]])
        )
    elif payment_type == "credit":
        await message.answer(
            base_text + "🤝 <b>To'lov: Nasiya</b>\n\nAdmin nasiya shartlarini ko'rib chiqadi. Tez orada bog'lanishadi 📞",
            parse_mode="HTML"
        )
    else:  # cash - borib olish
        await message.answer(
            base_text + "🚶 <b>To'lov: Borib olish</b>\n\n" + SHOP_ADDRESS,
            parse_mode="HTML"
        )

    # ─── Adminga xabar (rasm + ma'lumot) ─────────────────────────────────────
    payment_label = PAYMENT_EMOJI.get(payment_type, payment_text)
    nasiya_note = "\n⚠️ <b>NASIYA — alohida ko'rib chiqing!</b>" if payment_type == "credit" else ""

    admin_text = (
        f"🆕 <b>YANGI BUYURTMA #{order.id}</b>{nasiya_note}\n"
        f"{'─' * 28}\n"
        f"👤 {message.from_user.full_name}"
        f"{'  @' + message.from_user.username if message.from_user.username else ''}\n"
        f"📱 {user.phone or comment or '—'}\n"
        f"{'─' * 28}\n"
        f"📍 {address}\n"
        f"💳 {payment_label}\n"
        f"{'─' * 28}\n"
        f"{cart_lines}"
        f"{'─' * 28}\n"
        f"💰 <b>JAMI: {int(total):,} so'm</b>"
    )

    for admin_id in ADMIN_IDS:
        try:
            # Har bir mahsulot rasmi bilan yuborish
            for item in cart:
                async with AsyncSessionLocal() as session:
                    product = await get_product_by_id(session, item["product_id"])
                if product and product.photo_url:
                    s = f" ({item['size']})" if item.get('size') else ""
                    b = f" | ✍️ {item['back_print']}" if item.get('back_print') else ""
                    p = f" | ✍️ {item['player_name']}" if item.get('player_name') else ""
                    caption = f"🖼 <b>{product.name}</b>{s}{b}{p}\n💰 {int(item['price']):,} so'm × {item['qty']}"
                    await bot.send_photo(
                        admin_id,
                        photo=product.photo_url,
                        caption=caption,
                        parse_mode="HTML"
                    )

            # Asosiy buyurtma xabari + tugmalar
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

    msg = NOTIFY_MESSAGES.get(new_status, "")
    if not msg:
        return

    # Nasiya tasdiqlanganda — Paynet linki ham yuboriladi
    if new_status == "confirmed" and order.payment_type and order.payment_type.value == "credit":
        try:
            await bot.send_message(
                order.user.telegram_id,
                f"📦 <b>Buyurtma #{order_id}</b>\n\n{msg}\n\n"
                f"💰 To'lov summasi: <b>{int(order.total_price):,} so'm</b>\n"
                "👇 To'lov uchun:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💳 Paynet orqali to'lash", url=PAYNET_LINK)
                ]])
            )
        except Exception as e:
            print(f"Mijozga xabar yuborishda xato: {e}")

    # Borib olish tasdiqlanganda — do'kon manzili yuboriladi
    elif new_status == "confirmed" and order.payment_type and order.payment_type.value == "cash":
        try:
            await bot.send_message(
                order.user.telegram_id,
                f"📦 <b>Buyurtma #{order_id}</b>\n\n{msg}\n\n" + SHOP_ADDRESS,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Mijozga xabar yuborishda xato: {e}")

    else:
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
