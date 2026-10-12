from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import async_session
from bot.services.cycle_service import get_or_create_user
from bot.services.i18n import t
from bot.keyboards.inline import lang_select, main_menu, role_select_keyboard, partner_main_menu

router = Router()

LANGS = {"uz", "ru", "en", "kk", "tg", "ky"}


class SetupStates(StatesGroup):
    waiting_cycle_len = State()
    waiting_period_len = State()


async def send_welcome(message: Message, lang: str = "uz"):
    await message.answer(t(lang, "welcome"), reply_markup=lang_select(), parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.first_name = message.from_user.first_name
        user.username = message.from_user.username
        await session.commit()
        lang = user.language
        if not user.onboarded:
            await send_welcome(message, lang)
            return
        name = message.from_user.first_name or "gulim"
        if user.role == "partner":
            await message.answer(f"💙 {name}!", reply_markup=partner_main_menu(lang))
            return
        from bot.handlers.cycle import build_status
        status = await build_status(user, session)
    await message.answer(
        t(lang, "main_menu", name=name, status=status),
        reply_markup=main_menu(lang), parse_mode="HTML"
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"🆔 <code>{message.from_user.id}</code>", parse_mode="HTML")


@router.callback_query(F.data.startswith("setup_lang:"))
async def set_language(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    if lang not in LANGS:
        await call.answer()
        return
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.language = lang
        user.first_name = call.from_user.first_name
        user.username = call.from_user.username
        await session.commit()
    await state.clear()
    await call.message.edit_text(t(lang, "lang_set"))
    await call.message.answer(t(lang, "choose_role"), reply_markup=role_select_keyboard(lang))
    await call.answer()


@router.callback_query(F.data == "setup_role:woman")
async def set_role_woman(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.role = "woman"
        lang = user.language
        await session.commit()
    await call.message.edit_text(t(lang, "ask_cycle_len"), parse_mode="HTML")
    await state.set_state(SetupStates.waiting_cycle_len)
    await call.answer()


@router.callback_query(F.data == "setup_role:partner")
async def set_role_partner(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.role = "partner"
        user.onboarded = True
        lang = user.language
        await session.commit()
    await call.message.edit_text(t(lang, "partner_welcome"), parse_mode="HTML")
    await call.message.answer("💙", reply_markup=partner_main_menu(lang))
    await state.clear()
    await call.answer()


@router.message(SetupStates.waiting_cycle_len)
async def set_cycle_len(message: Message, state: FSMContext):
    try:
        days = max(20, min(45, int((message.text or "").strip())))
    except ValueError:
        days = 28
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.avg_cycle_length = days
        lang = user.language
        await session.commit()
    await message.answer(t(lang, "ask_period_len"), parse_mode="HTML")
    await state.set_state(SetupStates.waiting_period_len)


@router.message(SetupStates.waiting_period_len)
async def set_period_len(message: Message, state: FSMContext):
    try:
        days = max(2, min(10, int((message.text or "").strip())))
    except ValueError:
        days = 5
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        user.avg_period_length = days
        user.onboarded = True
        lang = user.language
        await session.commit()
    await message.answer(t(lang, "setup_done"), reply_markup=main_menu(lang), parse_mode="HTML")
    await state.clear()
