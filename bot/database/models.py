from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlalchemy import BigInteger, Integer, String, Boolean, Date, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language: Mapped[str] = mapped_column(String(5), default="uz")
    avg_cycle_length: Mapped[int] = mapped_column(Integer, default=28)
    avg_period_length: Mapped[int] = mapped_column(Integer, default=5)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cycles: Mapped[list["Cycle"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    symptoms: Mapped[list["Symptom"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cycle_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="cycles")


class Symptom(Base):
    __tablename__ = "symptoms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    flow: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    pain_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="symptoms")
