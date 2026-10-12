from __future__ import annotations
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import User, Cycle, Symptom
from bot.services.timeutil import today

MIN_CYCLE, MAX_CYCLE = 18, 50
MAX_PERIOD = 12
AVG_WINDOW = 6


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


async def get_latest_cycle(session: AsyncSession, user_id: int) -> Optional[Cycle]:
    """Most recent cycle by start date, whether still active or finished."""
    result = await session.execute(
        select(Cycle).where(Cycle.user_id == user_id).order_by(desc(Cycle.start_date)).limit(1)
    )
    return result.scalar_one_or_none()


async def recalc_user_stats(session: AsyncSession, user_id: int) -> None:
    """Recompute each cycle's length and the user's averages from recorded history.

    cycle_length on a cycle is the gap from the previous cycle's start to its own start.
    Gaps outside a plausible range (a skipped month, a mis-tap) are kept but not averaged.
    """
    user = await session.get(User, user_id)
    if not user:
        return
    cycles = (await session.execute(
        select(Cycle).where(Cycle.user_id == user_id).order_by(Cycle.start_date)
    )).scalars().all()

    prev = None
    for c in cycles:
        c.cycle_length = (c.start_date - prev.start_date).days if prev else None
        prev = c

    lengths = [c.cycle_length for c in cycles if c.cycle_length and MIN_CYCLE <= c.cycle_length <= MAX_CYCLE]
    if lengths:
        recent = lengths[-AVG_WINDOW:]
        user.avg_cycle_length = round(sum(recent) / len(recent))

    durations = [(c.end_date - c.start_date).days + 1 for c in cycles if c.end_date]
    durations = [d for d in durations if 1 <= d <= MAX_PERIOD]
    if durations:
        recent = durations[-AVG_WINDOW:]
        user.avg_period_length = round(sum(recent) / len(recent))


async def recalc_all_users(session: AsyncSession) -> None:
    user_ids = (await session.execute(select(Cycle.user_id).distinct())).scalars().all()
    for uid in user_ids:
        await recalc_user_stats(session, uid)
    await session.commit()


async def start_cycle(session: AsyncSession, user_id: int) -> Optional[Cycle]:
    active = await get_active_cycle(session, user_id)
    if active:
        return None
    cycle = Cycle(user_id=user_id, start_date=today())
    session.add(cycle)
    await session.flush()
    await recalc_user_stats(session, user_id)
    await session.commit()
    return cycle


async def end_cycle(session: AsyncSession, user_id: int, custom_end_date: Optional[date] = None) -> Optional[Cycle]:
    active = await get_active_cycle(session, user_id)
    if not active:
        return None
    active.end_date = max(custom_end_date or today(), active.start_date)
    await session.flush()
    await recalc_user_stats(session, user_id)
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


async def get_predictions(session: AsyncSession, user: User) -> Optional[dict]:
    latest = await get_latest_cycle(session, user.id)
    if not latest:
        return None
    next_period = compute_next_period(latest.start_date, user.avg_cycle_length)
    ovulation = compute_ovulation(next_period)
    return {
        "next_period": next_period,
        "ovulation": ovulation,
        "pms_start": compute_pms_start(ovulation),
        "active": latest.end_date is None,
        "latest_start": latest.start_date,
    }


async def upsert_symptom(
    session: AsyncSession,
    user_id: int,
    flow: Optional[str] = None,
    pain_level: Optional[int] = None,
    pain_types: Optional[str] = None,
    mood: Optional[str] = None,
    notes: Optional[str] = None,
) -> Symptom:
    day = today()
    result = await session.execute(
        select(Symptom).where(Symptom.user_id == user_id, Symptom.date == day).order_by(Symptom.id)
    )
    symptom = result.scalars().first()
    if not symptom:
        symptom = Symptom(user_id=user_id, date=day)
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
        symptom.notes = f"{symptom.notes}\n{notes}" if symptom.notes else notes
    await session.commit()
    return symptom
