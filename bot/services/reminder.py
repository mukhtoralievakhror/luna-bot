from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from aiogram import Bot

from bot.database.db import async_session
from bot.database.models import User
from bot.services.cycle_service import get_last_cycle, compute_next_period, compute_ovulation, compute_pms_start
from bot.services.i18n import t


async def send_reminders(bot: Bot):
    today = date.today()
    async with async_session() as session:
        result = await session.execute(select(User).where(User.reminder_enabled == True))
        users = result.scalars().all()

    for user in users:
        try:
            last = await _get_last(user.id)
            if not last:
                continue
            next_period = compute_next_period(last.start_date, user.avg_cycle_length)
            ovulation = compute_ovulation(next_period)
            pms_start = compute_pms_start(ovulation)
            days_until = (next_period - today).days
            lang = user.language

            if days_until == user.reminder_days_before:
                await bot.send_message(user.id, t(lang, "reminder_period", days=days_until))
            elif today == ovulation:
                await bot.send_message(user.id, t(lang, "reminder_ovulation"))
            elif today == pms_start:
                await bot.send_message(user.id, t(lang, "reminder_pms"))

            if user.partner_id and user.partner_notify:
                try:
                    async with async_session() as psession:
                        from bot.database.models import User as UserModel
                        partner = await psession.get(UserModel, user.partner_id)
                    if partner:
                        p_lang = partner.language
                        if days_until == user.reminder_days_before:
                            await bot.send_message(user.partner_id, t(p_lang, "partner_notify_period", days=days_until))
                        elif today == ovulation:
                            await bot.send_message(user.partner_id, t(p_lang, "partner_notify_ovulation"))
                        elif today == pms_start:
                            await bot.send_message(user.partner_id, t(p_lang, "partner_notify_pms"))
                except Exception:
                    pass
        except Exception:
            pass


async def _get_last(user_id: int):
    async with async_session() as session:
        return await get_last_cycle(session, user_id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(send_reminders, "cron", hour=9, minute=0, args=[bot])
    return scheduler
