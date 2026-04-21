from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from database.db import AsyncSessionLocal
from database.crud import (
    get_all_categories, get_all_products, get_product_by_id,
    create_product, update_product, delete_product, get_pending_orders, get_order_with_items
)
from bot.middlewares.admin_check import is_admin, ADMIN_IDS
from bot.keyboards.admin_kb import admin_menu_kb, order_actions_kb, product_manage_kb
from bot.keyboards.main_menu import main_menu_kb

router = Router()


def admin_only(func):
    """Admin tekshirish dekorator"""
    async def wrapper(message: Message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Siz admin emassiz!")
            return
        return await func(message, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


class AddProductState(StatesGroup):
    category = State()
    name = State()
    description = State()
    price = State()
    discount = State()
    photo = State()


class EditPriceState(StatesGroup):
    waiting_price = State()
    product_id = State()


class EditDiscountState(StatesGroup):
    waiting_discount = State()
    product_id = State()


# ==================== ADMIN PANEL ====================

@router.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Ruxsat yo'q!")
        return
    await message.answer(
        "⚙️ <b>Admin Panel</b>\n\nNimani qilmoqchisiz?",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )


@router.message(F.text == "🏠 Asosiy menyu")
async def back_to_main(message: Message):
    admin = is_admin(message.from_user.id)
    await message.answer("🏠 Asosiy menyu", reply_markup=main_menu_kb(is_admin=admin))


# ==================== YANGI BUYURTMALAR ====================

@router.message(F.text == "📋 Yangi buyurtmalar")
async def show_pending_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        orders = await get_pending_orders(session)

    if not orders:
        await message.answer("✅ Yangi buyurtmalar yo'q")
        return

    await message.answer(f"📋 <b>{len(orders)} ta yangi buyurtma:</b>", parse_mode="HTML")

    for order in orders:
        text = (
            f"🆕 <b>Buyurtma #{order.id}</b>\n"
            f"👤 {order.user.full_name}\n"
            f"📱 ID: <code>{order.user.telegram_id}</code>\n"
            f"📍 {order.delivery_address}\n"
            f"💰 {int(order.total_price):,} so'm\n"
            f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=order_actions_kb(order.id))


@router.message(F.text == "📊 Barcha buyurtmalar")
async def show_all_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    from database.crud import get_all_orders
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session, limit=20)

    if not orders:
        await message.answer("Buyurtmalar yo'q")
        return

    STATUS_EMOJI = {
        "pending": "⏳",
        "confirmed": "✅",
        "delivering": "🚚",
        "done": "✔️",
        "cancelled": "❌",
    }

    text = f"📊 <b>So'nggi {len(orders)} ta buyurtma:</b>\n\n"
    for order in orders:
        emoji = STATUS_EMOJI.get(order.status.value, "❓")
        text += f"{emoji} #{order.id} | {order.user.full_name} | {int(order.total_price):,} so'm\n"

    await message.answer(text, parse_mode="HTML")


# ==================== MAHSULOTLAR ====================

@router.message(F.text == "📦 Mahsulotlar")
async def list_products(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        products = await get_all_products(session)

    if not products:
        await message.answer("Mahsulotlar yo'q")
        return

    for product in products:
        text = (
            f"<b>{product.name}</b> (ID: {product.id})\n"
            f"💰 Narx: {int(product.price):,} so'm"
        )
        if product.discount_percent > 0:
            text += f" | Skidka: {int(product.discount_percent)}%"
        await message.answer(text, parse_mode="HTML", reply_markup=product_manage_kb(product.id))


# ==================== MAHSULOT QO'SHISH ====================

@router.message(F.text == "➕ Mahsulot qo'shish")
async def start_add_product(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        categories = await get_all_categories(session)

    text = "📦 <b>Kategoriyani tanlang (raqam yuboring):</b>\n\n"
    for cat in categories:
        text += f"{cat.id}. {cat.emoji} {cat.name}\n"

    await state.set_state(AddProductState.category)
    await message.answer(text, parse_mode="HTML")


@router.message(AddProductState.category)
async def add_product_name(message: Message, state: FSMContext):
    try:
        category_id = int(message.text)
        await state.update_data(category_id=category_id)
        await state.set_state(AddProductState.name)
        await message.answer("✏️ Mahsulot nomini yozing:")
    except ValueError:
        await message.answer("⚠️ Raqam yuboring")


@router.message(AddProductState.name)
async def add_product_description(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProductState.description)
    await message.answer("📝 Tavsif yozing (o'tkazib yuborish uchun - yuboring):")


@router.message(AddProductState.description)
async def add_product_price(message: Message, state: FSMContext):
    desc = None if message.text == "-" else message.text
    await state.update_data(description=desc)
    await state.set_state(AddProductState.price)
    await message.answer("💰 Narxni yozing (faqat raqam, so'mda):")


@router.message(AddProductState.price)
async def add_product_discount(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "").replace(" ", ""))
        await state.update_data(price=price)
        await state.set_state(AddProductState.discount)
        await message.answer("🏷 Skidka foizini yozing (0 = yo'q):")
    except ValueError:
        await message.answer("⚠️ Faqat raqam yuboring")


@router.message(AddProductState.discount)
async def add_product_photo(message: Message, state: FSMContext):
    try:
        discount = float(message.text)
        await state.update_data(discount=discount)
        await state.set_state(AddProductState.photo)
        await message.answer("📸 Rasm yuboring (o'tkazib yuborish uchun - yuboring):")
    except ValueError:
        await message.answer("⚠️ Faqat raqam yuboring (masalan: 10)")


@router.message(AddProductState.photo)
async def save_new_product(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_url = None

    if message.photo:
        photo_url = message.photo[-1].file_id
    elif message.text != "-":
        photo_url = message.text

    async with AsyncSessionLocal() as session:
        product = await create_product(
            session,
            category_id=data["category_id"],
            name=data["name"],
            description=data.get("description"),
            price=data["price"],
            discount_percent=data.get("discount", 0),
            photo_url=photo_url,
            is_active=True,
            in_stock=True
        )

    await state.clear()
    await message.answer(
        f"✅ <b>Mahsulot qo'shildi!</b>\n\n"
        f"📦 {product.name}\n"
        f"💰 {int(product.price):,} so'm",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )


# ==================== NARX O'ZGARTIRISH ====================

@router.callback_query(F.data.startswith("edit_price_"))
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.set_state(EditPriceState.waiting_price)
    await state.update_data(product_id=product_id)
    await callback.message.answer(f"💰 Yangi narxni yozing (so'mda):")
    await callback.answer()


@router.message(EditPriceState.waiting_price)
async def save_new_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "").replace(" ", ""))
        data = await state.get_data()
        async with AsyncSessionLocal() as session:
            await update_product(session, data["product_id"], price=price)
        await state.clear()
        await message.answer(f"✅ Narx yangilandi: <b>{int(price):,} so'm</b>", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Faqat raqam yuboring")


# ==================== SKIDKA O'ZGARTIRISH ====================

@router.callback_query(F.data.startswith("edit_discount_"))
async def start_edit_discount(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.set_state(EditDiscountState.waiting_discount)
    await state.update_data(product_id=product_id)
    await callback.message.answer("🏷 Yangi skidka foizini yozing (0-100):")
    await callback.answer()


@router.message(EditDiscountState.waiting_discount)
async def save_new_discount(message: Message, state: FSMContext):
    try:
        discount = float(message.text)
        if not 0 <= discount <= 100:
            await message.answer("⚠️ 0 dan 100 gacha raqam yuboring")
            return
        data = await state.get_data()
        async with AsyncSessionLocal() as session:
            await update_product(session, data["product_id"], discount_percent=discount)
        await state.clear()
        await message.answer(f"✅ Skidka yangilandi: <b>{int(discount)}%</b>", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Faqat raqam yuboring")


# ==================== MAHSULOT O'CHIRISH ====================

@router.callback_query(F.data.startswith("delete_prod_"))
async def delete_product_callback(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        await update_product(session, product_id, is_active=False)
    await callback.message.edit_text("🗑 Mahsulot o'chirildi")
    await callback.answer("✅ O'chirildi")


# ==================== WEB PANEL LINK ====================

@router.message(F.text == "🌐 Web Panel")
async def web_panel_link(message: Message):
    if not is_admin(message.from_user.id):
        return
    web_url = os.getenv("WEB_PANEL_URL", "Railway deploy qilingandan keyin URL bo'ladi")
    await message.answer(
        f"🌐 <b>Web Admin Panel:</b>\n\n{web_url}\n\n"
        f"🔑 Parol: .env da ADMIN_PANEL_SECRET",
        parse_mode="HTML"
    )


import os
