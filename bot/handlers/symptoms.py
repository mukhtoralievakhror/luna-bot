import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.database.db import async_session
from bot.database.models import User
from bot.services.cycle_service import upsert_symptom
from bot.services.i18n import t
from bot.keyboards.inline import (
    holat_menu_keyboard, flow_keyboard, pain_keyboard, mood_keyboard,
    pain_types_keyboard, main_menu, PAIN_TYPES, PAIN_FROM_CODE,
)

router = Router()

FLOWS = {"light", "medium", "heavy"}
MOODS = {"happy", "sad", "irritable", "tired", "normal"}

BTN_SYMPTOMS = {
    "uz": "💊 Bugungi holat", "ru": "💊 Самочувствие сегодня", "en": "💊 Today's wellbeing",
    "kk": "💊 Бүгінгі жағдай", "tg": "💊 Ҳоли имрӯза", "ky": "💊 Бүгүнкү абал",
}

# Callback data carries the whole flow state (chain flag, chosen pain types) so the
# buttons keep working after a restart wipes in-memory FSM storage.
# chain=1: started from "magical day started" → pain → mood; chain=0: single answer.


async def _lang(user_id: int) -> str:
    async with async_session() as session:
        user = await session.get(User, user_id)
        return user.language if user else "uz"


def _chain(parts: list, idx: int) -> bool:
    return len(parts) > idx and parts[idx] == "1"


def _selected_from_markup(call: CallbackQuery) -> list:
    markup = call.message.reply_markup if call.message else None
    selected = []
    for row in (markup.inline_keyboard if markup else []):
        for btn in row:
            data = btn.callback_data or ""
            if data.startswith("ptype:") and btn.text.startswith("✅"):
                selected.append(data.split(":")[1])
    return [pt for pt in PAIN_TYPES if pt in selected]


async def _finish(call: CallbackQuery, lang: str, text_key: str):
    await call.message.edit_text(t(lang, text_key))
    await call.message.answer("🌸", reply_markup=main_menu(lang))


@router.message(F.text.in_(BTN_SYMPTOMS.values()))
async def ask_holat(message: Message):
    async with async_session() as session:
        user = await session.get(User, message.from_user.id)
        if user.role == "partner":
            return
        lang = user.language
    await message.answer(t(lang, "holat_menu_prompt"), reply_markup=holat_menu_keyboard(lang))


@router.callback_query(F.data == "holat:oqim")
async def holat_oqim(call: CallbackQuery):
    lang = await _lang(call.from_user.id)
    await call.message.edit_text(t(lang, "flow_question"), reply_markup=flow_keyboard(lang, chain=False))
    await call.answer()


@router.callback_query(F.data.in_({"holat:pain", "proactive_pain"}))
async def holat_pain(call: CallbackQuery):
    lang = await _lang(call.from_user.id)
    await call.message.edit_text(t(lang, "pain_types_question"), reply_markup=pain_types_keyboard(lang, []))
    await call.answer()


@router.callback_query(F.data.startswith("flow:"))
async def got_flow(call: CallbackQuery):
    parts = call.data.split(":")
    flow = parts[1]
    if flow not in FLOWS:
        await call.answer()
        return
    # Buttons sent before this format existed only came from the cycle-start chain.
    chain = _chain(parts, 2) if len(parts) > 2 else True
    lang = await _lang(call.from_user.id)
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, flow=flow)
    if chain:
        await call.message.edit_text(t(lang, "pain_types_question"), reply_markup=pain_types_keyboard(lang, [], chain=True))
    else:
        await _finish(call, lang, "symptom_saved")
    await call.answer()


@router.callback_query(F.data.startswith("ptype:"))
async def toggle_pain_type(call: CallbackQuery):
    parts = call.data.split(":")
    pt = parts[1]
    chain = _chain(parts, 2)
    lang = await _lang(call.from_user.id)
    selected = _selected_from_markup(call)
    if pt in selected:
        selected.remove(pt)
    elif pt in PAIN_TYPES:
        selected.append(pt)
    await call.message.edit_reply_markup(reply_markup=pain_types_keyboard(lang, selected, chain))
    await call.answer()


@router.callback_query(F.data.startswith("ptype_none"))
async def pain_type_none(call: CallbackQuery):
    chain = _chain(call.data.split(":"), 1)
    lang = await _lang(call.from_user.id)
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, pain_level=0, pain_types="[]")
    if chain:
        await call.message.edit_text(t(lang, "mood_question"), reply_markup=mood_keyboard(lang))
    else:
        await _finish(call, lang, "pain_types_saved")
    await call.answer()


@router.callback_query(F.data.startswith("ptype_done"))
async def pain_types_done(call: CallbackQuery):
    chain = _chain(call.data.split(":"), 1)
    lang = await _lang(call.from_user.id)
    selected = _selected_from_markup(call)
    if not selected:
        await call.answer(t(lang, "pain_types_need_one"), show_alert=True)
        return
    await call.message.edit_text(t(lang, "pain_question"), reply_markup=pain_keyboard(lang, chain, selected))
    await call.answer()


@router.callback_query(F.data.startswith("pain:"))
async def got_pain_level(call: CallbackQuery):
    parts = call.data.split(":")
    if parts[1] not in {"0", "1", "3", "5"}:
        await call.answer()
        return
    pain = int(parts[1])
    chain = _chain(parts, 2)
    codes = parts[3] if len(parts) > 3 else ""
    types = [PAIN_FROM_CODE[c] for c in codes if c in PAIN_FROM_CODE]
    lang = await _lang(call.from_user.id)
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, pain_level=pain, pain_types=json.dumps(types))
    if chain:
        await call.message.edit_text(t(lang, "mood_question"), reply_markup=mood_keyboard(lang))
    else:
        await _finish(call, lang, "pain_types_saved")
    await call.answer()


@router.callback_query(F.data.startswith("mood:"))
async def got_mood(call: CallbackQuery):
    mood = call.data.split(":")[1]
    if mood not in MOODS:
        await call.answer()
        return
    lang = await _lang(call.from_user.id)
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, mood=mood)
    await _finish(call, lang, "symptom_saved")
    await call.answer()
