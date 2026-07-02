import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import async_session
from bot.services.cycle_service import get_or_create_user, upsert_symptom
from bot.services.i18n import t
from bot.keyboards.inline import (
    holat_menu_keyboard, flow_keyboard, pain_keyboard, mood_keyboard,
    pain_types_keyboard, main_menu,
)

router = Router()

BTN_SYMPTOMS = {
    "uz": "💊 Bugungi holat", "ru": "💊 Самочувствие сегодня", "en": "💊 Today's wellbeing",
    "kk": "💊 Бүгінгі жағдай", "tg": "💊 Ҳоли имрӯза", "ky": "💊 Бүгүнкү абал",
}


class SymptomStates(StatesGroup):
    waiting_pain = State()
    waiting_mood = State()
    waiting_pain_types = State()
    waiting_pain_lvl = State()


# ─── Entry point ──────────────────────────────────────────────────────────────

@router.message(F.text.in_(BTN_SYMPTOMS.values()))
async def ask_holat(message: Message, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        if user.role == "partner":
            return
    await state.update_data(lang=lang, user_id=message.from_user.id)
    await message.answer(t(lang, "holat_menu_prompt"), reply_markup=holat_menu_keyboard(lang))


# ─── Sub-menu: choose oqim or pain ───────────────────────────────────────────

@router.callback_query(F.data == "holat:oqim")
async def holat_oqim(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await call.message.edit_text(t(lang, "flow_question"), reply_markup=flow_keyboard(lang))
    await call.answer()


@router.callback_query(F.data == "holat:pain")
async def holat_pain(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await state.update_data(selected_pain_types=[])
    await call.message.edit_text(
        t(lang, "pain_types_question"),
        reply_markup=pain_types_keyboard(lang, []),
    )
    await state.set_state(SymptomStates.waiting_pain_types)
    await call.answer()


# ─── Flow path (existing) ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("flow:"))
async def got_flow(call: CallbackQuery, state: FSMContext):
    flow = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, flow=flow)
    await state.update_data(selected_pain_types=[], ask_mood=True)
    await call.message.edit_text(
        t(lang, "pain_types_question"),
        reply_markup=pain_types_keyboard(lang, []),
    )
    await state.set_state(SymptomStates.waiting_pain_types)
    await call.answer()


@router.callback_query(SymptomStates.waiting_mood, F.data.startswith("mood:"))
async def got_mood(call: CallbackQuery, state: FSMContext):
    mood = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, mood=mood)
    await call.message.edit_text(t(lang, "symptom_saved"))
    await call.message.answer("🌸", reply_markup=main_menu(lang))
    await state.clear()


# ─── Pain types path (new) ────────────────────────────────────────────────────

@router.callback_query(SymptomStates.waiting_pain_types, F.data.startswith("ptype:"))
async def toggle_pain_type(call: CallbackQuery, state: FSMContext):
    pt = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")
    selected = list(data.get("selected_pain_types", []))
    if pt in selected:
        selected.remove(pt)
    else:
        selected.append(pt)
    await state.update_data(selected_pain_types=selected)
    await call.message.edit_reply_markup(reply_markup=pain_types_keyboard(lang, selected))
    await call.answer()


@router.callback_query(SymptomStates.waiting_pain_types, F.data == "ptype_none")
async def pain_type_none(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    ask_mood = data.get("ask_mood", False)
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, pain_level=0, pain_types="[]")
    if ask_mood:
        await call.message.edit_text(t(lang, "mood_question"), reply_markup=mood_keyboard(lang))
        await state.set_state(SymptomStates.waiting_mood)
    else:
        await call.message.edit_text(t(lang, "pain_types_saved"))
        await call.message.answer("🌸", reply_markup=main_menu(lang))
        await state.clear()
    await call.answer()


@router.callback_query(SymptomStates.waiting_pain_types, F.data == "ptype_done")
async def pain_types_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    selected = data.get("selected_pain_types", [])
    if not selected:
        await call.answer("Kamida bitta og'riq turini tanlang yoki '😌 Og'riq yo'q' bosing.", show_alert=True)
        return
    await state.update_data(pain_types_json=json.dumps(selected))
    await call.message.edit_text(t(lang, "pain_question"), reply_markup=pain_keyboard(lang))
    await state.set_state(SymptomStates.waiting_pain_lvl)
    await call.answer()


@router.callback_query(SymptomStates.waiting_pain_lvl, F.data.startswith("pain:"))
async def got_pain_after_types(call: CallbackQuery, state: FSMContext):
    pain = int(call.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    ask_mood = data.get("ask_mood", False)
    pain_types_json = data.get("pain_types_json", "[]")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, pain_level=pain, pain_types=pain_types_json)
    if ask_mood:
        await call.message.edit_text(t(lang, "mood_question"), reply_markup=mood_keyboard(lang))
        await state.set_state(SymptomStates.waiting_mood)
    else:
        await call.message.edit_text(t(lang, "pain_types_saved"))
        await call.message.answer("🌸", reply_markup=main_menu(lang))
        await state.clear()
    await call.answer()


# ─── Proactive pain inquiry (from reminder) ───────────────────────────────────

@router.callback_query(F.data == "proactive_pain")
async def proactive_pain_start(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, call.from_user.id)
        lang = user.language
    await state.update_data(lang=lang, user_id=call.from_user.id, selected_pain_types=[])
    await call.message.edit_text(
        t(lang, "pain_types_question"),
        reply_markup=pain_types_keyboard(lang, []),
    )
    await state.set_state(SymptomStates.waiting_pain_types)
    await call.answer()
