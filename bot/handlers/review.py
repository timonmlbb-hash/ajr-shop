"""
Sharh (Review) tizimi:
- Buyurtma yetkazilgandan keyin bot avtomatik so'rov yuboradi
- Mijoz 5 yulduzdan biri + sharh yozadi
- Admin guruhga sharh ko'rinadi
- Boshqa mijozlar mahsulot sahifasida sharh ko'radi
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Review, User, Product
from bot.middlewares.admin_check import GROUP_CHAT_ID

router = Router()

STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


class ReviewState(StatesGroup):
    waiting_text = State()


def rating_kb(order_id: int, product_id: int = None) -> InlineKeyboardMarkup:
    prod_part = product_id or 0
    rows = [[
        InlineKeyboardButton(text="⭐", callback_data=f"review_1_{order_id}_{prod_part}"),
        InlineKeyboardButton(text="⭐⭐", callback_data=f"review_2_{order_id}_{prod_part}"),
        InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"review_3_{order_id}_{prod_part}"),
        InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"review_4_{order_id}_{prod_part}"),
        InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"review_5_{order_id}_{prod_part}"),
    ]]
    rows.append([InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"review_skip_{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ask_review(bot: Bot, user_telegram_id: int, order_id: int, product_id: int = None):
    """Buyurtma yakunlanganda chaqiriladi"""
    try:
        await bot.send_message(
            user_telegram_id,
            "🌟 <b>Xaridingizdan mamnunmisiz?</b>\n\n"
            "Iltimos, xizmatimizni baholang — bu bizga yaxshilanishga yordam beradi!\n\n"
            "⭐ = Yomon  |  ⭐⭐⭐⭐⭐ = A'lo",
            parse_mode="HTML",
            reply_markup=rating_kb(order_id, product_id)
        )
    except Exception as e:
        print(f"Sharh so'rovida xato: {e}")


@router.callback_query(F.data.startswith("review_skip_"))
async def skip_review(callback: CallbackQuery):
    await callback.message.edit_text("Keyingi safar baholashingizni kutamiz! 😊")
    await callback.answer()


@router.callback_query(F.data.startswith("review_") & ~F.data.startswith("review_skip_"))
async def handle_rating(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    rating   = int(parts[1])
    order_id = int(parts[2])
    product_id = int(parts[3]) if parts[3] != "0" else None

    await state.set_state(ReviewState.waiting_text)
    await state.update_data(rating=rating, order_id=order_id, product_id=product_id)

    await callback.message.edit_text(
        f"Siz {STARS[rating]} baho berdingiz!\n\n"
        "✍️ <b>Sharh yozing</b> (ixtiyoriy):\n"
        "<i>Masalan: Forma sifati zo'r, tez yetkazildi!</i>\n\n"
        "O'tkazib yuborish uchun — yuboring",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ReviewState.waiting_text)
async def save_review(message: Message, state: FSMContext, bot: Bot):
    data       = await state.get_data()
    rating     = data["rating"]
    order_id   = data["order_id"]
    product_id = data.get("product_id")
    text       = None if message.text.strip() == "-" else message.text.strip()

    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await state.clear()
            return

        review = Review(
            user_id=user.id,
            product_id=product_id,
            order_id=order_id,
            rating=rating,
            text=text,
            is_visible=True
        )
        session.add(review)
        await session.commit()

        # Mahsulot nomini olish
        prod_name = "Mahsulot"
        if product_id:
            pr = await session.get(Product, product_id)
            if pr:
                prod_name = pr.name

    await state.clear()
    await message.answer(
        f"🙏 <b>Rahmat!</b>\n\n"
        f"Sizning {STARS[rating]} bahoyingiz qabul qilindi.\n"
        f"Fikringiz bizga juda muhim! ⚽",
        parse_mode="HTML"
    )

    # Admin guruhga sharh yuborish
    review_text = (
        f"⭐ <b>YANGI SHARH</b>\n"
        f"{'─' * 24}\n"
        f"👤 {message.from_user.full_name}"
        f"{'  @' + message.from_user.username if message.from_user.username else ''}\n"
        f"🛍 {prod_name}\n"
        f"🔢 Buyurtma #{order_id}\n"
        f"{'─' * 24}\n"
        f"{STARS[rating]} ({rating}/5)\n"
    )
    if text:
        review_text += f"💬 <i>{text}</i>"

    try:
        await bot.send_message(GROUP_CHAT_ID, review_text, parse_mode="HTML")
    except Exception as e:
        print(f"Guruhga sharh yuborishda xato: {e}")
