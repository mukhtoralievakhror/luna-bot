import random
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import async_session
from bot.database.models import User, Cycle, Symptom
from bot.services.cycle_service import get_or_create_user, get_all_cycles
from bot.services.i18n import t
from bot.keyboards.inline import lang_select, main_menu, role_select_keyboard, partner_main_menu

router = Router()


class SetupStates(StatesGroup):
    waiting_cycle_len = State()
    waiting_period_len = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await session.get(User, message.from_user.id)
        if existing:
            existing.first_name = message.from_user.first_name
            existing.username = message.from_user.username
            await session.commit()
            lang = existing.language
            name = message.from_user.first_name or "gulim"
            await state.clear()
            if existing.role == "partner":
                await message.answer(f"💙 Salom, {name}!", reply_markup=partner_main_menu(lang))
            else:
                from bot.handlers.cycle import build_status
                status = await build_status(existing, session)
                await message.answer(
                    t(lang, "main_menu", name=name, status=status),
                    reply_markup=main_menu(lang), parse_mode="HTML"
                )
            return
        user = await get_or_create_user(session, message.from_user.id)
        user.first_name = message.from_user.first_name
        user.username = message.from_user.username
        await session.commit()
        lang = user.language
    await message.answer(t(lang, "welcome"), reply_markup=lang_select(), parse_mode="HTML")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"🆔 Sizning ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


@router.message(Command("seed"))
async def cmd_seed(message: Message):
    async with async_session() as session:
        existing_cycles = await get_all_cycles(session, message.from_user.id)
        if existing_cycles:
            await message.answer("⚠️ Allaqachon ma'lumot mavjud.")
            return
        user = await get_or_create_user(session, message.from_user.id)
        today = date.today()
        starts = [today - timedelta(days=d) for d in [91, 63, 35, 7]]
        for i, start in enumerate(starts):
            plen = random.choice([5, 6, 7])
            end = start + timedelta(days=plen)
            clen = (start - starts[i - 1]).days if i > 0 else None
            session.add(Cycle(
                user_id=message.from_user.id, start_date=start,
                end_date=end if i < len(starts) - 1 else None, cycle_length=clen,
            ))
            for d in range(plen):
                session.add(Symptom(
                    user_id=message.from_user.id,
                    date=start + timedelta(days=d),
                    flow=random.choice(['light', 'medium', 'medium', 'heavy', 'medium']),
                    pain_level=random.choice([1, 2, 3, 3, 4]),
                    mood=random.choice(['normal', 'tired', 'sad', 'irritable', 'normal']),
                ))
        user.avg_cycle_length = 28
        user.avg_period_length = 6
        await session.commit()
    await message.answer("✅ 3 oylik test ma'lumotlari qo'shildi!")


@router.callback_query(F.data.startswith("setup_lang:"))
async def set_language(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.language = lang
        await session.commit()
    await call.message.edit_text(t(lang, "lang_set"))
    await call.message.answer(t(lang, "choose_role"), reply_markup=role_select_keyboard(lang))
    await state.update_data(lang=lang)


@router.callback_query(F.data == "setup_role:woman")
async def set_role_woman(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.role = "woman"
        await session.commit()
    await call.message.edit_text(t(lang, "ask_cycle_len"), parse_mode="HTML")
    await state.set_state(SetupStates.waiting_cycle_len)


@router.callback_query(F.data == "setup_role:partner")
async def set_role_partner(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.role = "partner"
        await session.commit()
    await call.message.edit_text(t(lang, "partner_welcome"), parse_mode="HTML")
    await call.message.answer("💙", reply_markup=partner_main_menu(lang))
    await state.clear()


@router.message(SetupStates.waiting_cycle_len)
async def set_cycle_len(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    try:
        days = max(20, min(45, int(message.text.strip())))
    except ValueError:
        days = 28
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.avg_cycle_length = days
        await session.commit()
    await message.answer(t(lang, "ask_period_len"), parse_mode="HTML")
    await state.set_state(SetupStates.waiting_period_len)


@router.message(SetupStates.waiting_period_len)
async def set_period_len(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    try:
        days = max(2, min(10, int(message.text.strip())))
    except ValueError:
        days = 5
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.avg_period_length = days
        await session.commit()
    await message.answer(t(lang, "setup_done"), reply_markup=main_menu(lang), parse_mode="HTML")
    await state.clear()
