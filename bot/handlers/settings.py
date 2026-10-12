from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from sqlalchemy import delete, update

from bot.database.db import async_session
from bot.database.models import User, Cycle, Symptom, PartnerInvite
from bot.services.cycle_service import (
    get_or_create_user, get_all_cycles, get_predictions,
)
from bot.services.i18n import t
from bot.keyboards.inline import (
    main_menu, lang_select, lang_change_select, settings_keyboard, reset_confirm_keyboard,
    reminder_keyboard, partner_main_menu, pain_hour_keyboard
)

router = Router()

BTN_SETTINGS = {
    "uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings",
    "kk": "⚙️ Параметрлер", "tg": "⚙️ Танзимот", "ky": "⚙️ Жөндөөлөр",
}
BTN_REMINDERS = {
    "uz": "🔔 Eslatmalar", "ru": "🔔 Напоминания", "en": "🔔 Reminders",
    "kk": "🔔 Еске салулар", "tg": "🔔 Ёддоштҳо", "ky": "🔔 Эскертмелер",
}
LANG_NAMES = {"uz": "O'zbek", "ru": "Русский", "en": "English", "kk": "Қазақша", "tg": "Тоҷикӣ", "ky": "Кыргызча"}
LANGS = set(LANG_NAMES)


def _settings_text(user: User) -> str:
    return t(user.language, "settings_menu",
             language=LANG_NAMES.get(user.language, user.language),
             cycle=user.avg_cycle_length,
             period=user.avg_period_length)


def _reminder_view(user: User):
    lang = user.language
    status = t(lang, "reminder_on") if user.reminder_enabled else t(lang, "reminder_off")
    is_partner = user.role == "partner"
    if is_partner:
        text = t(lang, "partner_reminder_settings", status=status)
    else:
        text = t(lang, "reminder_settings", status=status, days=user.reminder_days_before)
    kb = reminder_keyboard(lang, user.reminder_enabled, user.reminder_days_before, is_partner)
    return text, kb


def _menu(user: User):
    return partner_main_menu(user.language) if user.role == "partner" else main_menu(user.language)


@router.message(F.text.in_(BTN_SETTINGS.values()))
async def show_settings(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
    await message.answer(_settings_text(user), reply_markup=settings_keyboard(user.language, user.role == "partner"), parse_mode="HTML")


@router.message(F.text.in_(BTN_REMINDERS.values()))
async def show_reminders(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
    text, kb = _reminder_view(user)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "settings:lang")
async def change_lang_menu(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
    await call.message.edit_text(t(user.language, "choose_lang"), reply_markup=lang_change_select())
    await call.answer()


@router.callback_query(F.data.startswith("change_lang:"))
async def update_lang(call: CallbackQuery):
    lang = call.data.split(":")[1]
    if lang not in LANGS:
        await call.answer()
        return
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.language = lang
        await session.commit()
        if user.role == "partner":
            status = ""
        else:
            from bot.handlers.cycle import build_status
            status = await build_status(user, session)
    await call.message.edit_text(t(lang, "lang_set"))
    await call.message.answer(
        t(lang, "main_menu", name=call.from_user.first_name or "gulim", status=status),
        reply_markup=_menu(user), parse_mode="HTML"
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
    uid = call.from_user.id
    async with async_session() as session:
        user = await get_or_create_user(session, uid)
        lang = user.language
        await session.execute(update(User).where(User.partner_id == uid).values(partner_id=None, partner_notify=False))
        await session.execute(delete(PartnerInvite).where(PartnerInvite.user_id == uid))
        await session.execute(delete(Symptom).where(Symptom.user_id == uid))
        await session.execute(delete(Cycle).where(Cycle.user_id == uid))
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()
    await state.clear()
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(t(lang, "reset_done"), reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await call.message.answer(t(lang, "welcome"), reply_markup=lang_select(), parse_mode="HTML")


@router.callback_query(F.data == "reset:no")
async def cancel_reset(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
    await call.message.edit_text(_settings_text(user), reply_markup=settings_keyboard(user.language, user.role == "partner"), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "settings:pain_time")
async def show_pain_time(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
    await call.message.edit_text(
        t(user.language, "settings_pain_time") + f"\n\n⏰ {user.pain_reminder_hour}:00",
        reply_markup=pain_hour_keyboard(user.language, user.pain_reminder_hour),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pain_hour:"))
async def set_pain_hour(call: CallbackQuery):
    hour = int(call.data.split(":")[1])
    if not 0 <= hour <= 23:
        await call.answer()
        return
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.pain_reminder_hour = hour
        lang = user.language
        await session.commit()
    await call.message.edit_text(t(lang, "pain_time_set", hour=hour))
    await call.answer()


@router.callback_query(F.data == "reminder:toggle")
async def toggle_reminder(call: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.reminder_enabled = not user.reminder_enabled
        await session.commit()
    text, kb = _reminder_view(user)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer(t(user.language, "reminder_toggle_on" if user.reminder_enabled else "reminder_toggle_off"))


@router.callback_query(F.data.startswith("reminder:days:"))
async def set_reminder_days(call: CallbackQuery):
    days = int(call.data.split(":")[2])
    if days not in (1, 2, 3):
        await call.answer()
        return
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        user.reminder_days_before = days
        await session.commit()
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(t(user.language, "reminder_days_set", n=days), reply_markup=_menu(user))


@router.message(F.text.in_({"📊 Mening tarixim", "📊 Моя история", "📊 My history", "📊 Менің тарихым", "📊 Таърихи ман", "📊 Менин тарыхым"}))
async def show_stats(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        cycles = await get_all_cycles(session, user.id)
        pred = await get_predictions(session, user)

    if not cycles:
        await message.answer(t(lang, "stats_no_data"))
        return

    text = t(lang, "stats_title")
    text += t(lang, "stats_avg_cycle", days=user.avg_cycle_length)
    text += t(lang, "stats_avg_period", days=user.avg_period_length)
    text += t(lang, "stats_total", count=len(cycles))
    if pred:
        text += t(lang, "stats_next", date=pred["next_period"].strftime("%d.%m.%Y"))
        text += t(lang, "stats_ovulation", date=pred["ovulation"].strftime("%d.%m.%Y"))

    await message.answer(text, parse_mode="HTML")
