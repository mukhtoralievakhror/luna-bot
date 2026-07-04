from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, text

from bot.database.db import async_session
from bot.database.models import User, Cycle, Symptom
from bot.config import BOT_TOKEN, ADMIN_SECRET
from bot.services.cycle_service import get_last_cycle, compute_next_period, compute_ovulation, compute_pms_start

router = APIRouter(prefix="/admin/api")


def _check(secret: str):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/stats")
async def get_stats(secret: str = Query(...)):
    _check(secret)
    async with async_session() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar()
        women = (await session.execute(select(func.count()).select_from(User).where(User.role == "woman"))).scalar()
        partners = (await session.execute(select(func.count()).select_from(User).where(User.role == "partner"))).scalar()
        partner_connections = (await session.execute(
            select(func.count()).select_from(User).where(User.partner_id.isnot(None))
        )).scalar()
        reminders_on = (await session.execute(
            select(func.count()).select_from(User).where(User.reminder_enabled == True)
        )).scalar()
        total_cycles = (await session.execute(select(func.count()).select_from(Cycle))).scalar()
        total_symptoms = (await session.execute(select(func.count()).select_from(Symptom))).scalar()

        today = date.today()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        new_today = (await session.execute(
            select(func.count()).select_from(User).where(func.date(User.created_at) == today)
        )).scalar()
        new_week = (await session.execute(
            select(func.count()).select_from(User).where(func.date(User.created_at) >= week_ago)
        )).scalar()
        new_month = (await session.execute(
            select(func.count()).select_from(User).where(func.date(User.created_at) >= month_ago)
        )).scalar()

        lang_rows = (await session.execute(
            select(User.language, func.count().label("cnt")).group_by(User.language).order_by(func.count().desc())
        )).all()

        # Daily new users last 30 days for chart
        growth_rows = (await session.execute(
            select(func.date(User.created_at).label("d"), func.count().label("cnt"))
            .where(func.date(User.created_at) >= month_ago)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )).all()

    return {
        "total_users": total_users,
        "women": women,
        "partners": partners,
        "partner_connections": partner_connections,
        "reminders_on": reminders_on,
        "total_cycles": total_cycles,
        "total_symptoms": total_symptoms,
        "new_today": new_today,
        "new_week": new_week,
        "new_month": new_month,
        "by_lang": [{"lang": r.language, "count": r.cnt} for r in lang_rows],
        "growth": [{"date": str(r.d), "count": r.cnt} for r in growth_rows],
    }


@router.get("/users")
async def list_users(
    secret: str = Query(...),
    page: int = Query(1, ge=1),
    lang: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
):
    _check(secret)
    limit = 50
    offset = (page - 1) * limit

    async with async_session() as session:
        q = select(User).order_by(User.created_at.desc())
        if lang:
            q = q.where(User.language == lang)
        if role:
            q = q.where(User.role == role)
        if search:
            try:
                uid = int(search)
                q = q.where(User.id == uid)
            except ValueError:
                pass

        count_q = select(func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar()
        users = (await session.execute(q.offset(offset).limit(limit))).scalars().all()

        result = []
        for u in users:
            cycle_count = (await session.execute(
                select(func.count()).select_from(Cycle).where(Cycle.user_id == u.id)
            )).scalar()
            result.append({
                "id": u.id,
                "first_name": u.first_name,
                "username": u.username,
                "language": u.language,
                "role": u.role,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "reminder_enabled": u.reminder_enabled,
                "partner_id": u.partner_id,
                "cycle_count": cycle_count,
            })

    return {"total": total, "page": page, "users": result}


@router.get("/users/{user_id}")
async def get_user_detail(user_id: int, secret: str = Query(...)):
    _check(secret)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        cycles = (await session.execute(
            select(Cycle).where(Cycle.user_id == user_id).order_by(Cycle.start_date.desc()).limit(10)
        )).scalars().all()

        symptom_count = (await session.execute(
            select(func.count()).select_from(Symptom).where(Symptom.user_id == user_id)
        )).scalar()

    return {
        "id": user.id,
        "language": user.language,
        "role": user.role,
        "avg_cycle_length": user.avg_cycle_length,
        "avg_period_length": user.avg_period_length,
        "reminder_enabled": user.reminder_enabled,
        "reminder_days_before": user.reminder_days_before,
        "partner_id": user.partner_id,
        "partner_notify": user.partner_notify,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "cycles": [
            {
                "id": c.id,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "cycle_length": c.cycle_length,
            }
            for c in cycles
        ],
        "symptom_count": symptom_count,
    }


class BroadcastBody(BaseModel):
    text: str
    target: str = "all"  # all | women | partners | uz | ru | en | kk | tg | ky


@router.post("/broadcast")
async def broadcast(secret: str = Query(...), body: BroadcastBody = ...):
    _check(secret)
    if not body.text.strip():
        raise HTTPException(400, "Text is empty")

    async with async_session() as session:
        q = select(User.id)
        if body.target == "women":
            q = q.where(User.role == "woman")
        elif body.target == "partners":
            q = q.where(User.role == "partner")
        elif body.target in ("uz", "ru", "en", "kk", "tg", "ky"):
            q = q.where(User.language == body.target)
        user_ids = (await session.execute(q)).scalars().all()

    from aiogram import Bot
    bot = Bot(token=BOT_TOKEN)
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, body.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await bot.session.close()

    return {"sent": sent, "failed": failed, "total": len(user_ids)}


@router.get("/broadcast/count")
async def broadcast_count(secret: str = Query(...), target: str = Query("all")):
    _check(secret)
    async with async_session() as session:
        q = select(func.count()).select_from(User)
        if target == "women":
            q = q.where(User.role == "woman")
        elif target == "partners":
            q = q.where(User.role == "partner")
        elif target in ("uz", "ru", "en", "kk", "tg", "ky"):
            q = q.where(User.language == target)
        count = (await session.execute(q)).scalar()
    return {"count": count}


@router.get("/health")
async def health(secret: str = Query(...)):
    _check(secret)
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    async with async_session() as session:
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar()
        cycle_count = (await session.execute(select(func.count()).select_from(Cycle))).scalar()
        symptom_count = (await session.execute(select(func.count()).select_from(Symptom))).scalar()

    return {
        "db": "ok" if db_ok else "error",
        "server_time": datetime.utcnow().isoformat() + "Z",
        "users": user_count,
        "cycles": cycle_count,
        "symptoms": symptom_count,
    }


@router.get("/debug/reminders")
async def debug_reminders(secret: str = Query(...)):
    """Show why each user did or did not receive a reminder today."""
    _check(secret)
    today = date.today()
    results = []

    async with async_session() as session:
        users = (await session.execute(
            select(User).where(User.role == "woman")
        )).scalars().all()

        for user in users:
            last = await get_last_cycle(session, user.id)
            entry: dict = {
                "id": user.id,
                "first_name": user.first_name,
                "username": user.username,
                "reminder_enabled": user.reminder_enabled,
                "language": user.language,
            }

            if not last:
                entry["reason"] = "no_cycle"
                entry["would_send"] = []
                results.append(entry)
                continue

            active_cycle = last if last.end_date is None else None
            next_period = compute_next_period(last.start_date, user.avg_cycle_length)
            ovulation = compute_ovulation(next_period)
            pms_start = compute_pms_start(ovulation)
            days_until = (next_period - today).days

            entry["last_cycle_start"] = last.start_date.isoformat()
            entry["last_cycle_end"] = last.end_date.isoformat() if last.end_date else None
            entry["next_period"] = next_period.isoformat()
            entry["days_until_period"] = days_until
            entry["ovulation"] = ovulation.isoformat()
            entry["pms_start"] = pms_start.isoformat()
            entry["active_cycle_day"] = (today - active_cycle.start_date).days + 1 if active_cycle else None

            would_send = []
            reasons_not_sent = []

            if not user.reminder_enabled:
                reasons_not_sent.append("reminder_disabled")
            else:
                if days_until == user.reminder_days_before:
                    would_send.append(f"reminder_period (days={days_until})")
                if today == ovulation:
                    would_send.append("reminder_ovulation")
                if today == pms_start:
                    would_send.append("reminder_pms")

                if active_cycle:
                    day_num = (today - active_cycle.start_date).days + 1
                    if 1 <= day_num <= 5:
                        would_send.append(f"period_message_morning (day {day_num})")
                        would_send.append(f"period_message_evening (day {day_num})")
                    else:
                        reasons_not_sent.append(f"active_cycle_day_{day_num}_outside_1_5")
                else:
                    reasons_not_sent.append("no_active_cycle")

                if not would_send and not reasons_not_sent:
                    reasons_not_sent.append(
                        f"no_trigger_today (days_until={days_until}, reminder_days_before={user.reminder_days_before})"
                    )

            entry["would_send"] = would_send
            entry["reasons_not_sent"] = reasons_not_sent
            results.append(entry)

    return {"today": today.isoformat(), "users": results}


@router.post("/trigger/reminders")
async def trigger_reminders(secret: str = Query(...), type: str = Query("all")):
    """Manually fire reminder jobs now. type=all|period|morning|evening|pain"""
    _check(secret)
    from aiogram import Bot as AiogramBot
    from bot.services.reminder import (
        send_reminders, send_period_messages, send_pain_reminders, check_unclosed_cycles
    )

    bot = AiogramBot(token=BOT_TOKEN)
    fired = []
    try:
        if type in ("all", "period"):
            await send_reminders(bot)
            fired.append("send_reminders")
        if type in ("all", "morning"):
            await send_period_messages(bot, "morning")
            fired.append("send_period_messages(morning)")
        if type in ("all", "evening"):
            await send_period_messages(bot, "evening")
            fired.append("send_period_messages(evening)")
        if type in ("all", "pain"):
            await send_pain_reminders(bot)
            fired.append("send_pain_reminders")
        if type in ("all", "cycle_check"):
            await check_unclosed_cycles(bot)
            fired.append("check_unclosed_cycles")
    finally:
        await bot.session.close()

    return {"fired": fired, "time": datetime.utcnow().isoformat() + "Z"}
