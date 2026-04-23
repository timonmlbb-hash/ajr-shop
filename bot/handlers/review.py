"""
Sharh tizimi:
- Pochta topshirilganda ask_review chaqiriladi
- Mijoz ⭐-⭐⭐⭐⭐⭐ bosadi → matn yozadi
- Sharh guruh chatga keladi
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

STARS = {
    1: "⭐ 1/5 — Yomon",
    2: "⭐⭐ 2/5 — Qoniqarsiz",
    3: "⭐⭐⭐ 3/5 — O'rtacha",
    4: "⭐⭐⭐⭐ 4/5 — Yaxshi",
    5: "⭐⭐⭐⭐⭐ 5/5 — A'lo!",
}
STAR_ICONS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


class ReviewState(StatesGroup):
    waiting_text = State()


def rating_kb(order_id: int, product_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1⭐", callback_data=f"rv_1_{order_id}_{product_id}"),
            InlineKeyboardButton(text="2⭐", callback_data=f"rv_2_{order_id}_{product_id}"),
            InlineKeyboardButton(text="3⭐", callback_data=f"rv_3_{order_id}_{product_id}"),
            InlineKeyboardButton(text="4⭐", callback_data=f"rv_4_{order_id}_{product_id}"),
            InlineKeyboardButton(text="5⭐", callback_data=f"rv_5_{order_id}_{product_id}"),
        ],
        [InlineKeyboardButton(text="⏭ Keyinroq", callback_data=f"rv_skip_{order_id}")],
    ])


async def ask_review(bot: Bot, user_telegram_id: int, order_id: int, product_id: int = None):
    """Admin 'Pochtaga topshirildi' bosganda chaqiriladi"""
    prod_id = product_id or 0
    try:
        await bot.send_message(
            user_telegram_id,
            "📦 <b>Buyurtmangiz qo'lingizga yetib bordimi?</b>\n\n"
            "Iltimos, xaridingiz haqida fikr bildiring!\n"
            "Bu bizning xizmatimizni yaxshilashga yordam beradi 🙏\n\n"
            "Quyidagi yulduzlardan birini bosing:",
            parse_mode="HTML",
            reply_markup=rating_kb(order_id, prod_id)
        )
    except Exception as e:
        print(f"Sharh so'rovida xato: {e}")


@router.callback_query(F.data.startswith("rv_skip_"))
async def skip_review(callback: CallbackQuery):
    await callback.message.edit_text(
        "Tushunarli! Keyingi xaridda ham kutamiz 😊⚽",
        reply_markup=None
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rv_") & ~F.data.startswith("rv_skip_"))
async def handle_rating(callback: CallbackQuery, state: FSMContext):
    parts    = callback.data.split("_")
    rating     = int(parts[1])
    order_id   = int(parts[2])
    product_id = int(parts[3]) if parts[3] != "0" else None

    await state.set_state(ReviewState.waiting_text)
    await state.update_data(rating=rating, order_id=order_id, product_id=product_id)

    await callback.message.edit_text(
        f"Siz <b>{STARS[rating]}</b> baho berdingiz!\n\n"
        "✍️ <b>Qisqacha sharh yozing:</b>\n"
        "<i>Masalan: Forma sifati zo'r, tez yetkazildi!</i>\n\n"
        "O'tkazib yuborish uchun <b>—</b> yuboring",
        parse_mode="HTML",
        reply_markup=None
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
        user_r = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user   = user_r.scalar_one_or_none()
        if not user:
            await state.clear()
            return

        prod_name = "Mahsulot"
        if product_id:
            pr = await session.get(Product, product_id)
            if pr:
                prod_name = pr.name

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

    await state.clear()
    await message.answer(
        f"🙏 <b>Rahmat!</b>\n\n"
        f"{STAR_ICONS[rating]} Bahoyingiz qabul qilindi.\n"
        f"Fikringiz bizga juda muhim! ⚽\n\n"
        "Keyingi xaridda ham kutamiz 😊",
        parse_mode="HTML"
    )

    # Guruh chatga yuborish
    review_text = (
        f"⭐ <b>YANGI SHARH</b>\n"
        f"{'─' * 24}\n"
        f"👤 {message.from_user.full_name}"
        f"{'  @' + message.from_user.username if message.from_user.username else ''}\n"
        f"🛍 {prod_name} | Buyurtma #{order_id}\n"
        f"{'─' * 24}\n"
        f"{STAR_ICONS[rating]} <b>({rating}/5)</b>\n"
    )
    if text:
        review_text += f"💬 <i>{text}</i>"

    try:
        await bot.send_message(GROUP_CHAT_ID, review_text, parse_mode="HTML")
    except Exception as e:
        print(f"Guruhga sharh yuborishda xato: {e}")
