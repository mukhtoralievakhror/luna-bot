from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.db import async_session
from bot.services.cycle_service import get_or_create_user
from bot.services.i18n import t
from bot.keyboards.inline import lang_select, main_menu, role_select_keyboard, partner_main_menu

router = Router()


class SetupStates(StatesGroup):
    waiting_cycle_len = State()
    waiting_period_len = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
    await message.answer(t(lang, "welcome"), reply_markup=lang_select(), parse_mode="HTML")


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
