import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.db import async_session
from bot.database.models import User, Cycle, Symptom
from bot.locales.period_messages import period_message
from bot.services.cycle_service import end_cycle, get_predictions
from bot.services.i18n import t
from bot.services.timeutil import TZ, today

log = logging.getLogger(__name__)

AUTO_CLOSE_DAY = 10


def auto_close_day(avg_period_length: int) -> int:
    return max(AUTO_CLOSE_DAY, avg_period_length + 3)


def _pain_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_daily_pain"), callback_data="proactive_pain"),
    ]])


async def _active_rows():
    async with async_session() as session:
        result = await session.execute(
            select(User, Cycle).join(Cycle, Cycle.user_id == User.id).where(
                User.role == "woman",
                Cycle.end_date.is_(None),
            )
        )
        return result.all()


async def send_reminders(bot: Bot):
    day = today()
    async with async_session() as session:
        women = (await session.execute(select(User).where(User.role == "woman"))).scalars().all()

    for user in women:
        try:
            async with async_session() as session:
                pred = await get_predictions(session, user)
                partner = await session.get(User, user.partner_id) if user.partner_id else None
            if not pred or pred["active"]:
                continue
            days_until = (pred["next_period"] - day).days
            if days_until == user.reminder_days_before:
                kind = "period"
            elif day == pred["ovulation"]:
                kind = "ovulation"
            elif day == pred["pms_start"]:
                kind = "pms"
            else:
                continue

            if user.reminder_enabled:
                await bot.send_message(user.id, t(user.language, f"reminder_{kind}", days=days_until))
            if partner and user.partner_notify and partner.reminder_enabled:
                await bot.send_message(partner.id, t(partner.language, f"partner_notify_{kind}", days=days_until))
        except Exception:
            log.exception("send_reminders failed for %s", user.id)


async def send_pain_reminders(bot: Bot):
    now_hour = datetime.now(TZ).hour
    day = today()
    async with async_session() as session:
        users = (await session.execute(
            select(User).where(
                User.role == "woman",
                User.reminder_enabled == True,
                User.pain_reminder_hour == now_hour,
            )
        )).scalars().all()

    for user in users:
        try:
            async with async_session() as session:
                pred = await get_predictions(session, user)
            if not pred or pred["active"]:
                continue
            days_until = (pred["next_period"] - day).days
            if days_until not in (3, 4):
                continue
            await bot.send_message(
                user.id,
                t(user.language, "pre_period_pain_ask", days=days_until),
                reply_markup=_pain_kb(user.language),
                parse_mode="HTML",
            )
        except Exception:
            log.exception("send_pain_reminders failed for %s", user.id)


async def check_unclosed_cycles(bot: Bot):
    """Past the usual period length, ask daily whether it's still going; auto-close on day 10."""
    day = today()
    for user, cycle in await _active_rows():
        try:
            elapsed = (day - cycle.start_date).days
            day_num = elapsed + 1
            lang = user.language

            if day_num >= auto_close_day(user.avg_period_length):
                end_date = min(cycle.start_date + timedelta(days=user.avg_period_length - 1), day)
                async with async_session() as session:
                    closed = await end_cycle(session, user.id, custom_end_date=end_date)
                if closed and user.reminder_enabled:
                    await bot.send_message(
                        user.id,
                        t(lang, "cycle_auto_closed", date=closed.end_date.strftime("%d.%m.%Y")),
                        parse_mode="HTML",
                    )
                continue

            if day_num <= user.avg_period_length or not user.reminder_enabled:
                continue
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "cycle_check_yes"), callback_data="cycle_check:yes"),
                InlineKeyboardButton(text=t(lang, "cycle_check_no"), callback_data="cycle_check:no"),
            ]])
            await bot.send_message(
                user.id,
                t(lang, "cycle_check_question", days=elapsed),
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            log.exception("check_unclosed_cycles failed for %s", user.id)


async def send_period_messages(bot: Bot, time_of_day: str):
    day = today()
    for user, cycle in await _active_rows():
        try:
            if not user.reminder_enabled:
                continue
            msg = period_message(user.language, (day - cycle.start_date).days + 1, time_of_day)
            if msg:
                await bot.send_message(user.id, msg, parse_mode="HTML")
        except Exception:
            log.exception("send_period_messages failed for %s", user.id)


async def send_daily_pain_check(bot: Bot):
    day = today()
    for user, cycle in await _active_rows():
        try:
            if not user.reminder_enabled:
                continue
            async with async_session() as session:
                reported = (await session.execute(
                    select(Symptom.id).where(
                        Symptom.user_id == user.id,
                        Symptom.date == day,
                        Symptom.pain_level.isnot(None),
                    ).limit(1)
                )).scalar_one_or_none()
            if reported:
                continue
            await bot.send_message(
                user.id,
                t(user.language, "daily_pain_ask"),
                reply_markup=_pain_kb(user.language),
                parse_mode="HTML",
            )
        except Exception:
            log.exception("send_daily_pain_check failed for %s", user.id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(send_reminders, "cron", hour=9, minute=0, args=[bot])
    scheduler.add_job(send_pain_reminders, "cron", minute=0, args=[bot])
    scheduler.add_job(check_unclosed_cycles, "cron", hour=9, minute=5, args=[bot])
    scheduler.add_job(send_period_messages, "cron", hour=9, minute=10, args=[bot, "morning"])
    scheduler.add_job(send_period_messages, "cron", hour=20, minute=0, args=[bot, "evening"])
    scheduler.add_job(send_daily_pain_check, "cron", hour=11, minute=0, args=[bot])
    return scheduler
