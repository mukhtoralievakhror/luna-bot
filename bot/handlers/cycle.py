from datetime import date
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.db import async_session
from bot.services.cycle_service import (
    get_or_create_user, get_active_cycle, start_cycle, end_cycle,
    get_last_cycle, compute_next_period, compute_ovulation, compute_pms_start, get_all_cycles,
)
from bot.services.i18n import t
from bot.keyboards.inline import main_menu, flow_keyboard

router = Router()

BTN_START = {"uz": "🌺 Sehrli kun boshlandi", "ru": "🌺 Волшебный день начался", "en": "🌺 Magical day started"}
BTN_END = {"uz": "🌼 Sehrli kun tugadi", "ru": "🌼 Волшебный день завершился", "en": "🌼 Magical day ended"}


def _is_btn(text: str, mapping: dict) -> bool:
    return text in mapping.values()


@router.message(F.text.func(lambda t: _is_btn(t, BTN_START)))
async def handle_start(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        cycle = await start_cycle(session, message.from_user.id)
    if cycle is None:
        await message.answer(t(lang, "cycle_already_active"))
        return
    await message.answer(t(lang, "cycle_started"), reply_markup=flow_keyboard(lang), parse_mode="HTML")


@router.message(F.text.func(lambda t: _is_btn(t, BTN_END)))
async def handle_end(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        cycle = await end_cycle(session, message.from_user.id)
    if cycle is None:
        await message.answer(t(lang, "cycle_not_active"))
        return
    await message.answer(t(lang, "cycle_ended"), reply_markup=main_menu(lang), parse_mode="HTML")


async def build_status(user, session) -> str:
    lang = user.language
    active = await get_active_cycle(session, user.id)
    if active:
        return t(lang, "status_active", start_date=active.start_date.strftime("%d.%m.%Y"))

    last = await get_last_cycle(session, user.id)
    if not last:
        return t(lang, "status_no_data")

    next_period = compute_next_period(last.start_date, user.avg_cycle_length)
    days_left = (next_period - date.today()).days
    ovulation = compute_ovulation(next_period)
    pms_start = compute_pms_start(ovulation)

    status = t(lang, "status_next", days=max(0, days_left), next_date=next_period.strftime("%d.%m.%Y"))
    status += "\n" + t(lang, "status_ovulation", date=ovulation.strftime("%d.%m.%Y"))
    status += "\n" + t(lang, "status_pms", date=pms_start.strftime("%d.%m.%Y"))
    return status
