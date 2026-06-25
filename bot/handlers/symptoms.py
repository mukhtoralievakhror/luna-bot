from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import async_session
from bot.services.cycle_service import get_or_create_user, upsert_symptom
from bot.services.i18n import t
from bot.keyboards.inline import flow_keyboard, pain_keyboard, mood_keyboard, main_menu

router = Router()

BTN_SYMPTOMS = {
    "uz": "💊 Bugungi holat", "ru": "💊 Самочувствие сегодня", "en": "💊 Today's wellbeing",
    "kk": "💊 Бүгінгі жағдай", "tg": "💊 Ҳоли имрӯза", "ky": "💊 Бүгүнкү абал",
}


class SymptomStates(StatesGroup):
    waiting_pain = State()
    waiting_mood = State()


@router.message(F.text.in_(BTN_SYMPTOMS.values()))
async def ask_flow(message: Message, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user.id)
        lang = user.language
        if user.role == "partner":
            return
    await message.answer(t(lang, "flow_question"), reply_markup=flow_keyboard(lang))
    await state.update_data(lang=lang, user_id=message.from_user.id)


@router.callback_query(F.data.startswith("flow:"))
async def got_flow(call: CallbackQuery, state: FSMContext):
    flow = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, flow=flow)
    await call.message.edit_text(t(lang, "pain_question"), reply_markup=pain_keyboard(lang))
    await state.set_state(SymptomStates.waiting_pain)


@router.callback_query(SymptomStates.waiting_pain, F.data.startswith("pain:"))
async def got_pain(call: CallbackQuery, state: FSMContext):
    pain = int(call.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, pain_level=pain)
    await call.message.edit_text(t(lang, "mood_question"), reply_markup=mood_keyboard(lang))
    await state.set_state(SymptomStates.waiting_mood)


@router.callback_query(SymptomStates.waiting_mood, F.data.startswith("mood:"))
async def got_mood(call: CallbackQuery, state: FSMContext):
    mood = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")
    async with async_session() as session:
        await upsert_symptom(session, call.from_user.id, mood=mood)
        user = await get_or_create_user(session, call.from_user.id)
    await call.message.edit_text(t(lang, "symptom_saved"))
    await call.message.answer("🌸", reply_markup=main_menu(lang))
    await state.clear()
