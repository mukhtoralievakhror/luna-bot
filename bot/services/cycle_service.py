from __future__ import annotations
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import User, Cycle, Symptom


async def get_or_create_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
    return user


async def get_active_cycle(session: AsyncSession, user_id: int) -> Optional[Cycle]:
    result = await session.execute(
        select(Cycle)
        .where(Cycle.user_id == user_id, Cycle.end_date.is_(None))
        .order_by(desc(Cycle.start_date))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_last_cycle(session: AsyncSession, user_id: int) -> Optional[Cycle]:
    result = await session.execute(
        select(Cycle)
        .where(Cycle.user_id == user_id, Cycle.end_date.isnot(None))
        .order_by(desc(Cycle.start_date))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_cycle(session: AsyncSession, user_id: int) -> Optional[Cycle]:
    active = await get_active_cycle(session, user_id)
    if active:
        return None
    cycle = Cycle(user_id=user_id, start_date=date.today())
    session.add(cycle)
    await session.commit()
    return cycle


async def end_cycle(session: AsyncSession, user_id: int, custom_end_date: Optional[date] = None) -> Optional[Cycle]:
    active = await get_active_cycle(session, user_id)
    if not active:
        return None
    active.end_date = custom_end_date or date.today()
    duration = (active.end_date - active.start_date).days
    user = await session.get(User, user_id)

    last = await get_last_cycle(session, user_id)
    if last:
        active.cycle_length = (active.start_date - last.start_date).days
        cycles = await get_all_cycles(session, user_id)
        lengths = [c.cycle_length for c in cycles if c.cycle_length]
        if lengths:
            user.avg_cycle_length = sum(lengths) // len(lengths)

    user.avg_period_length = max(1, (user.avg_period_length + duration) // 2)
    await session.commit()
    return active


async def get_all_cycles(session: AsyncSession, user_id: int) -> list[Cycle]:
    result = await session.execute(
        select(Cycle).where(Cycle.user_id == user_id).order_by(desc(Cycle.start_date))
    )
    return result.scalars().all()


def compute_next_period(last_start: date, cycle_length: int) -> date:
    return last_start + timedelta(days=cycle_length)


def compute_ovulation(next_period: date) -> date:
    return next_period - timedelta(days=14)


def compute_pms_start(ovulation: date) -> date:
    return ovulation + timedelta(days=5)


async def upsert_symptom(
    session: AsyncSession,
    user_id: int,
    flow: Optional[str] = None,
    pain_level: Optional[int] = None,
    pain_types: Optional[str] = None,
    mood: Optional[str] = None,
    notes: Optional[str] = None,
) -> Symptom:
    today = date.today()
    result = await session.execute(
        select(Symptom).where(Symptom.user_id == user_id, Symptom.date == today)
    )
    symptom = result.scalar_one_or_none()
    if not symptom:
        symptom = Symptom(user_id=user_id, date=today)
        session.add(symptom)
    if flow is not None:
        symptom.flow = flow
    if pain_level is not None:
        symptom.pain_level = pain_level
    if pain_types is not None:
        symptom.pain_types = pain_types
    if mood is not None:
        symptom.mood = mood
    if notes is not None:
        symptom.notes = notes
    await session.commit()
    return symptom
