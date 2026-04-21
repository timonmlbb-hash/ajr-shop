from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float,
    Boolean, DateTime, ForeignKey, Enum
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class OrderStatus(str, enum.Enum):
    PENDING = "pending"        # Yangi
    CONFIRMED = "confirmed"    # Tasdiqlangan
    DELIVERING = "delivering"  # Yetkazilmoqda
    DONE = "done"              # Yetkazildi
    CANCELLED = "cancelled"    # Bekor qilindi


class PaymentType(str, enum.Enum):
    CASH = "cash"        # Naqd
    CARD = "card"        # Karta
    CREDIT = "credit"    # Nasiya


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    full_name = Column(String(255))
    username = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    orders = relationship("Order", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    emoji = Column(String(10), default="📦")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    discount_percent = Column(Float, default=0)  # skidka foizi
    photo_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    in_stock = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")

    @property
    def final_price(self):
        if self.discount_percent > 0:
            return self.price * (1 - self.discount_percent / 100)
        return self.price


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    payment_type = Column(Enum(PaymentType), nullable=True)
    delivery_address = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    total_price = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    price_at_order = Column(Float, nullable=False)  # sotib olingan paytdagi narx
    size = Column(String(20), nullable=True)        # o'lcham (S, M, L, XL...)
    player_name = Column(String(100), nullable=True) # ism yozish xizmati

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
