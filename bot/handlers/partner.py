import secrets
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, delete, func

from bot.database.db import async_session
from bot.database.models import User, Cycle, PartnerInvite
from bot.keyboards.inline import partner_keyboard, partner_confirm_keyboard, partner_main_menu
from bot.services.i18n import t

router = Router()

LANGS = {"uz", "ru", "en", "kk", "tg", "ky"}
PARTNER_CODE = r"(?i)^[A-F0-9]{6}$"


async def _get_user(session, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def _valid_invite(session, code: str) -> PartnerInvite | None:
    invite = (await session.execute(
        select(PartnerInvite).where(PartnerInvite.code == code)
    )).scalar_one_or_none()
    if not invite or invite.expires_at < datetime.utcnow():
        return None
    return invite


@router.callback_query(F.data == "settings:partner")
async def partner_menu(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        lang = user.language
        has_partner = user.partner_id is not None
    text = t(lang, "partner_menu_active") if has_partner else t(lang, "partner_menu_none")
    await call.message.edit_text(text, reply_markup=partner_keyboard(lang, has_partner))
    await call.answer()


@router.callback_query(F.data == "settings:partner:generate")
async def partner_generate(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        lang = user.language
        await session.execute(delete(PartnerInvite).where(PartnerInvite.user_id == call.from_user.id))
        code = secrets.token_hex(3).upper()
        session.add(PartnerInvite(
            user_id=call.from_user.id,
            code=code,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        ))
        await session.commit()

    await call.message.edit_text(
        t(lang, "partner_code_generated", code=code),
        reply_markup=partner_keyboard(lang, has_partner=False),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data == "settings:partner:disconnect")
async def partner_disconnect(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        lang = user.language
        user.partner_id = None
        user.partner_notify = False
        await session.commit()

    await call.message.edit_text(t(lang, "partner_disconnected"), reply_markup=partner_keyboard(lang, has_partner=False))
    await call.answer()


@router.message(F.text.regexp(PARTNER_CODE))
async def connect_code(message: Message):
    code = message.text.strip().upper()
    requester_id = message.from_user.id

    async with async_session() as session:
        man = await _get_user(session, requester_id)
        if not man:
            tg_lang = (message.from_user.language_code or "")[:2]
            man = User(
                id=requester_id, role="partner", onboarded=True,
                language=tg_lang if tg_lang in LANGS else "uz",
                first_name=message.from_user.first_name, username=message.from_user.username,
            )
            session.add(man)
            await session.commit()
        m_lang = man.language

        invite = await _valid_invite(session, code)
        if not invite:
            await message.answer(t(m_lang, "partner_code_not_found"))
            return
        if invite.user_id == requester_id:
            await message.answer(t(m_lang, "partner_self_code"))
            return

        woman = await _get_user(session, invite.user_id)
        if not woman:
            await message.answer(t(m_lang, "partner_code_not_found"))
            return
        w_lang = woman.language

    man_name = message.from_user.full_name or message.from_user.first_name or "Partner"
    try:
        await message.bot.send_message(
            invite.user_id,
            t(w_lang, "partner_request_to_woman", name=man_name),
            reply_markup=partner_confirm_keyboard(w_lang, code, requester_id),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(t(m_lang, "error"))
        return

    await message.answer("✅")


@router.callback_query(F.data.startswith("partner:confirm:"))
async def partner_confirm(call: CallbackQuery):
    parts = call.data.split(":")
    woman_id = call.from_user.id
    async with async_session() as session:
        woman = await _get_user(session, woman_id)
        w_lang = woman.language if woman else "uz"
        # Older buttons lacked the requester id, so they can't be honoured safely.
        if len(parts) < 4 or not parts[3].isdigit():
            await call.answer(t(w_lang, "partner_code_not_found"), show_alert=True)
            return
        code, man_id = parts[2], int(parts[3])

        invite = await _valid_invite(session, code)
        if not invite or invite.user_id != woman_id or man_id == woman_id:
            await call.answer(t(w_lang, "partner_code_not_found"), show_alert=True)
            return

        man = await _get_user(session, man_id)
        if not man:
            await call.answer(t(w_lang, "partner_code_not_found"), show_alert=True)
            return
        m_lang = man.language

        woman.partner_id = man_id
        woman.partner_notify = True
        man.onboarded = True
        man_cycles = (await session.execute(
            select(func.count()).select_from(Cycle).where(Cycle.user_id == man_id)
        )).scalar()
        # Don't strip the tracker menu from someone who logs their own cycles.
        if not man_cycles:
            man.role = "partner"
        await session.execute(delete(PartnerInvite).where(PartnerInvite.code == code))
        await session.commit()
        man_is_partner = man.role == "partner"

    await call.message.edit_text(t(w_lang, "partner_connected_woman"))
    await call.answer()

    try:
        await call.bot.send_message(
            man_id, t(m_lang, "partner_connected_man"),
            reply_markup=partner_main_menu(m_lang) if man_is_partner else None,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("partner:reject:"))
async def partner_reject(call: CallbackQuery):
    code = call.data.split(":")[2]
    async with async_session() as session:
        await session.execute(delete(PartnerInvite).where(
            PartnerInvite.code == code, PartnerInvite.user_id == call.from_user.id
        ))
        await session.commit()
        user = await _get_user(session, call.from_user.id)
        lang = user.language if user else "uz"

    await call.message.edit_text(t(lang, "partner_rejected"))
    await call.answer()
