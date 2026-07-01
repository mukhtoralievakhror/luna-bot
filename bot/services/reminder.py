from datetime import date, datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.db import async_session
from bot.database.models import User, Cycle
from bot.services.cycle_service import get_last_cycle, compute_next_period, compute_ovulation, compute_pms_start
from bot.services.i18n import t

PERIOD_MESSAGES = {
    1: {
        "morning": "Sehrli kunlaringiz boshlandi, azizim 🌸\n\nBugun tanangiz siz uchun qattiq ishlayapti.\nIssiq choy, yumshoq plaid va ozgina dam —\nbugun bularni haqiqatan loyiq ko'rasiz 💕\n\nBiz yongingizdamiz 🌙",
        "evening": "Kechqurun bo'ldi, jonim 🌙\n\nBugungi kun qanday o'tdi?\nTanangiz bugun ko'p ish qildi — unga rahmat ayting 🥹\n\nErtaga biroz yengilroq bo'ladi, va'da beramiz 🌸\nYaxshi uxlang, azizim 💤",
    },
    2: {
        "morning": "Xayrli tong, gulim 🌺\n\nSehrli kunlarning 2-kuni —\nba'zida bu kun biroz og'irroq tuyulishi mumkin.\n\nBu tanangizning kuchi, zaiflik emas 💪🏻\nBugun sevgan ovqatingizni yeb ko'ring 🍵",
        "evening": "Siz bugun ham ajoyib edingiz 🌟\n\nOg'riq bo'lgan bo'lsa ham, davom ettingiz —\nbu kuch 🌸\n\nIssiq suv qoplama va yoqimli musiqa —\nbugun kechqurun siz uchun 🎵💕",
    },
    3: {
        "morning": "Assalomu alaykum, rayhonginam 🌿\n\n3-kun — ko'pchilik bugun biroz yengil his qiladi.\nTanangiz siz bilan birga ishlayapti 🤝\n\nBugun ozgina yurish, toza havo —\ntanangiz xursand bo'ladi 🍃",
        "evening": "Kechqurun, chiroyli qizim 🌙\n\nOynaga qarang —\nu yerda kuchli, go'zal bir ayol turibdi 🪞✨\n\nErtaga yanada yaxshiroq bo'lasiz,\nishoning 💛",
    },
    4: {
        "morning": "Hayrli tong, aziz qizim 🌼\n\n4-kun — energiya asta qaytmoqda 🌱\n\nBugun nimaga xursand bo'ldingiz?\nBitta narsa bo'lsa ham yetarli 💛",
        "evening": "Kechqurun, yulduzim ⭐\n\nBugungi og'riqlar kamaygandir, deb umid qilamiz 🌸\n\nAgar hali ham sezayotgan bo'lsangiz —\nbu ham o'tadi, har doim o'tadi 🌊\n\nErtaga yangilanish boshlanadi 🌙",
    },
    5: {
        "morning": "Xayrli tong, sevgilim 🌟\n\nSehrli kunlarning so'nggi kuni!\nTanangiz bu oyda ham mo'jizasini yaratdi 🌸\n\nBugun o'zingizni tabriklang —\nsiz har oyda bu kuchni olib yurasiz 💪🏻✨",
        "evening": "Va sehrli kunlar tugadi, gulim 🌺\n\nBu oyda o'zingizga g'amxo'r bo'ldingizmi?\nUmid qilamiz 💕\n\nEndi yangilanish davri boshlanadi —\neneriya, kayfiyat, hayot qaytadi 🌱\n\nKeyingi sehrli kunlar kelguncha\no'zingizni asrang, azizim 🌸\n\nLuna har doim yonginizda 🌙",
    },
}

TZ = ZoneInfo("Asia/Tashkent")


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


async def send_pain_reminders(bot: Bot):
    now_hour = datetime.now(TZ).hour
    today = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.role == "woman",
                User.reminder_enabled == True,
                User.pain_reminder_hour == now_hour,
            )
        )
        users = result.scalars().all()

    for user in users:
        try:
            last = await _get_last(user.id)
            if not last:
                continue
            next_period = compute_next_period(last.start_date, user.avg_cycle_length)
            days_until = (next_period - today).days
            if days_until not in (3, 4):
                continue
            lang = user.language
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "btn_daily_pain"), callback_data="proactive_pain"),
            ]])
            await bot.send_message(
                user.id,
                t(lang, "pre_period_pain_ask", days=days_until),
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            pass


async def check_unclosed_cycles(bot: Bot):
    today = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(User, Cycle).join(Cycle, Cycle.user_id == User.id).where(
                User.role == "woman",
                Cycle.end_date == None,
            )
        )
        rows = result.all()

    for user, cycle in rows:
        try:
            day_num = (today - cycle.start_date).days
            if day_num != 4:
                continue
            lang = user.language
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "cycle_check_yes"), callback_data="cycle_check:yes"),
                InlineKeyboardButton(text=t(lang, "cycle_check_no"), callback_data="cycle_check:no"),
            ]])
            await bot.send_message(
                user.id,
                t(lang, "cycle_check_question", days=day_num),
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            pass


async def send_period_messages(bot: Bot, time_of_day: str):
    today = date.today()
    async with async_session() as session:
        result = await session.execute(
            select(User, Cycle).join(Cycle, Cycle.user_id == User.id).where(
                User.role == "woman",
                Cycle.end_date == None,
            )
        )
        rows = result.all()

    for user, cycle in rows:
        try:
            day_num = (today - cycle.start_date).days + 1
            if day_num not in PERIOD_MESSAGES:
                continue
            msg = PERIOD_MESSAGES[day_num][time_of_day]
            await bot.send_message(user.id, msg, parse_mode="HTML")
        except Exception:
            pass


async def _get_last(user_id: int):
    async with async_session() as session:
        return await get_last_cycle(session, user_id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(send_reminders, "cron", hour=9, minute=0, args=[bot])
    scheduler.add_job(send_pain_reminders, "cron", minute=0, args=[bot])
    scheduler.add_job(check_unclosed_cycles, "cron", hour=9, minute=5, args=[bot])
    scheduler.add_job(send_period_messages, "cron", hour=9, minute=10, args=[bot, "morning"])
    scheduler.add_job(send_period_messages, "cron", hour=20, minute=0, args=[bot, "evening"])
    return scheduler
