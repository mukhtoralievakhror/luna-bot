from aiogram import Router, F
from aiogram.types import Message

from bot.database.db import async_session
from bot.database.models import User
from bot.services.cycle_service import upsert_symptom
from bot.services.i18n import t
from bot.keyboards.inline import main_menu, partner_main_menu

# Registered last: only messages no other handler claimed reach here.
router = Router()

MAX_NOTE = 1000


@router.message(F.text & ~F.text.startswith("/"))
async def save_note(message: Message):
    async with async_session() as session:
        user = await session.get(User, message.from_user.id)
        lang = user.language
        if user.role == "partner":
            await message.answer(t(lang, "menu_hint"), reply_markup=partner_main_menu(lang))
            return
        await upsert_symptom(session, user.id, notes=message.text.strip()[:MAX_NOTE])
    await message.answer(t(lang, "note_saved"), reply_markup=main_menu(lang))


@router.message()
async def fallback(message: Message):
    async with async_session() as session:
        user = await session.get(User, message.from_user.id)
    lang = user.language
    kb = partner_main_menu(lang) if user.role == "partner" else main_menu(lang)
    await message.answer(t(lang, "menu_hint"), reply_markup=kb)
