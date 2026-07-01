from datetime import date, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.db import async_session
from bot.services.cycle_service import (
    get_or_create_user, get_active_cycle, start_cycle, end_cycle,
    get_last_cycle, compute_next_period, compute_ovulation, compute_pms_start, get_all_cycles,
)
from bot.services.i18n import t
from bot.keyboards.inline import main_menu, flow_keyboard

router = Router()

BTN_START = {
    "uz": "🌺 Sehrli kun boshlandi", "ru": "🌺 Волшебный день начался", "en": "🌺 Magical day started",
    "kk": "🌺 Сиқырлы күн басталды", "tg": "🌺 Рӯзи ҷодугарӣ оғоз шуд", "ky": "🌺 Сыйкырлуу күн башталды",
}
BTN_END = {
    "uz": "🌼 Sehrli kun tugadi", "ru": "🌼 Волшебный день завершился", "en": "🌼 Magical day ended",
    "kk": "🌼 Сиқырлы күн аяқталды", "tg": "🌼 Рӯзи ҷодугарӣ ба охир расид", "ky": "🌼 Сыйкырлуу күн аяктады",
}


def _is_btn(text: str, mapping: dict) -> bool:
    return text in mapping.values()


@router.message(F.text.func(lambda t: _is_btn(t, BTN_START)))
async def handle_start(message: Message, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        if user.role == "partner":
            return
        cycle = await start_cycle(session, message.from_user.id)
    if cycle is None:
        await message.answer(t(lang, "cycle_already_active"))
        return
    await state.update_data(lang=lang, user_id=message.from_user.id)
    await message.answer(t(lang, "cycle_started"), reply_markup=flow_keyboard(lang), parse_mode="HTML")


@router.message(F.text.func(lambda t: _is_btn(t, BTN_END)))
async def handle_end(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        if user.role == "partner":
            return
        cycle = await end_cycle(session, message.from_user.id)
    if cycle is None:
        await message.answer(t(lang, "cycle_not_active"))
        return
    await message.answer(t(lang, "cycle_ended"), reply_markup=main_menu(lang), parse_mode="HTML")


@router.callback_query(F.data == "cycle_check:yes")
async def cycle_check_yes(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
    await call.message.edit_text(t(lang, "cycle_check_yes_response"))
    await call.answer()


@router.callback_query(F.data == "cycle_check:no")
async def cycle_check_no(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "cycle_end_today"), callback_data="cycle_end:0"),
            InlineKeyboardButton(text=t(lang, "cycle_end_1ago"), callback_data="cycle_end:1"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "cycle_end_2ago"), callback_data="cycle_end:2"),
            InlineKeyboardButton(text=t(lang, "cycle_end_3ago"), callback_data="cycle_end:3"),
        ],
    ])
    await call.message.edit_text(t(lang, "cycle_check_when_ended"), reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("cycle_end:"))
async def cycle_end_manual(call: CallbackQuery):
    days_ago = int(call.data.split(":")[1])
    end_date = date.today() - timedelta(days=days_ago)
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
        cycle = await end_cycle(session, call.from_user.id, custom_end_date=end_date)
    if cycle is None:
        await call.answer()
        return
    await call.message.edit_text(
        t(lang, "cycle_ended_manual", date=end_date.strftime("%d.%m.%Y")),
        parse_mode="HTML",
    )
    await call.answer()


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
