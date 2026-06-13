import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Float, JSON, DateTime, Boolean
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./escrow.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class TransactionModel(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True)
    paypal_order_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)
    payment_method = Column(String, default="paypal")
    amount = Column(Float)
    currency = Column(String, default="USD")
    status = Column(String, default="pending")
    sender_id = Column(String)
    receiver_id = Column(String)
    tx_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class MerchantModel(Base):
    __tablename__ = "merchants"

    id = Column(String, primary_key=True, index=True)
    paypal_business_email = Column(String, unique=True, index=True)
    merchant_id = Column(String, nullable=True)
    is_authorized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
