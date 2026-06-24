from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import delete

from bot.database.db import async_session
from bot.database.models import User, Cycle, Symptom
from bot.services.cycle_service import (
    get_or_create_user, get_all_cycles, get_last_cycle,
    compute_next_period, compute_ovulation,
)
from bot.services.i18n import t
from bot.keyboards.inline import (
    main_menu, lang_change_select, settings_keyboard, reset_confirm_keyboard, reminder_keyboard
)

router = Router()

BTN_SETTINGS = {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings"}
BTN_REMINDERS = {"uz": "🔔 Eslatmalar", "ru": "🔔 Напоминания", "en": "🔔 Reminders"}


@router.message(F.text.in_(BTN_SETTINGS.values()))
async def show_settings(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        lang_names = {"uz": "O'zbek", "ru": "Русский", "en": "English"}
        text = t(lang, "settings_menu",
                 language=lang_names.get(lang, lang),
                 cycle=user.avg_cycle_length,
                 period=user.avg_period_length)
    await message.answer(text, reply_markup=settings_keyboard(lang), parse_mode="HTML")


@router.message(F.text.in_(BTN_REMINDERS.values()))
async def show_reminders(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        status = t(lang, "reminder_on") if user.reminder_enabled else t(lang, "reminder_off")
        text = t(lang, "reminder_settings", status=status, days=user.reminder_days_before)
    await message.answer(text, reply_markup=reminder_keyboard(lang, user.reminder_enabled), parse_mode="HTML")


@router.callback_query(F.data == "settings:lang")
async def change_lang_menu(call: CallbackQuery):
    await call.message.edit_text(t("uz", "choose_lang"), reply_markup=lang_change_select())
    await call.answer()


@router.callback_query(F.data.startswith("change_lang:"))
async def update_lang(call: CallbackQuery):
    lang = call.data.split(":")[1]
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.language = lang
        await session.commit()
    await call.message.edit_text(t(lang, "lang_set"))
    await call.message.answer(
        t(lang, "main_menu", name=call.from_user.first_name or "gulim", status=""),
        reply_markup=main_menu(lang), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "settings:reset")
async def confirm_reset(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
    await call.message.edit_text(t(lang, "reset_confirm"), reply_markup=reset_confirm_keyboard(lang), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "reset:yes")
async def do_reset(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
        await session.execute(delete(Symptom).where(Symptom.user_id == call.from_user.id))
        await session.execute(delete(Cycle).where(Cycle.user_id == call.from_user.id))
        await session.execute(delete(User).where(User.id == call.from_user.id))
        await session.commit()
    await state.clear()
    await call.message.edit_text(t(lang, "reset_done"), parse_mode="HTML")
    await call.message.answer(t(lang, "welcome"), reply_markup=lang_select(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "reset:no")
async def cancel_reset(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
        lang_names = {"uz": "O'zbek", "ru": "Русский", "en": "English"}
        text = t(lang, "settings_menu",
                 language=lang_names.get(lang, lang),
                 cycle=user.avg_cycle_length,
                 period=user.avg_period_length)
    await call.message.edit_text(text, reply_markup=settings_keyboard(lang), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "reminder:toggle")
async def toggle_reminder(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.reminder_enabled = not user.reminder_enabled
        await session.commit()
        lang = user.language
        status = t(lang, "reminder_on") if user.reminder_enabled else t(lang, "reminder_off")
        text = t(lang, "reminder_settings", status=status, days=user.reminder_days_before)
    await call.message.edit_text(text, reply_markup=reminder_keyboard(lang, user.reminder_enabled), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("reminder:days:"))
async def set_reminder_days(call: CallbackQuery):
    days = int(call.data.split(":")[2])
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.reminder_days_before = days
        await session.commit()
        lang = user.language
        status = t(lang, "reminder_on") if user.reminder_enabled else t(lang, "reminder_off")
        text = t(lang, "reminder_settings", status=status, days=days)
    await call.answer(f"✅ {days} kun")
    await call.message.edit_text(text, reply_markup=reminder_keyboard(lang, user.reminder_enabled), parse_mode="HTML")


@router.message(F.text.in_({"📊 Mening tarixim", "📊 Моя история", "📊 My history"}))
async def show_stats(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        cycles = await get_all_cycles(session, user.id)
        last = await get_last_cycle(session, user.id)

    if not cycles:
        await message.answer(t(lang, "stats_no_data"))
        return

    text = t(lang, "stats_title")
    text += t(lang, "stats_avg_cycle", days=user.avg_cycle_length)
    text += t(lang, "stats_avg_period", days=user.avg_period_length)
    text += t(lang, "stats_total", count=len(cycles))

    if last:
        next_period = compute_next_period(last.start_date, user.avg_cycle_length)
        ovulation = compute_ovulation(next_period)
        text += t(lang, "stats_next", date=next_period.strftime("%d.%m.%Y"))
        text += t(lang, "stats_ovulation", date=ovulation.strftime("%d.%m.%Y"))

    await message.answer(text, parse_mode="HTML")
