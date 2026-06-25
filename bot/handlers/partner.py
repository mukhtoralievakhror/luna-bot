import secrets
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, delete

from bot.database.db import async_session
from bot.database.models import User, PartnerInvite
from bot.keyboards.inline import partner_keyboard, partner_confirm_keyboard
from bot.services.i18n import t

router = Router()


async def _get_user(session, user_id: int) -> User | None:
    return await session.get(User, user_id)


@router.callback_query(F.data == "settings:partner")
async def partner_menu(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        if not user:
            return
        lang = user.language
        has_partner = user.partner_id is not None
        text = t(lang, "partner_menu_active") if has_partner else t(lang, "partner_menu_none")
    await call.message.edit_text(text, reply_markup=partner_keyboard(lang, has_partner))
    await call.answer()


@router.callback_query(F.data == "settings:partner:generate")
async def partner_generate(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        if not user:
            return
        lang = user.language

        # Delete old invite for this user if exists
        await session.execute(delete(PartnerInvite).where(PartnerInvite.user_id == call.from_user.id))

        code = secrets.token_hex(3).upper()
        invite = PartnerInvite(
            user_id=call.from_user.id,
            code=code,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        session.add(invite)
        await session.commit()

    await call.message.edit_text(
        t(lang, "partner_code_generated", code=code),
        reply_markup=partner_keyboard(lang, has_partner=False),
    )
    await call.answer()


@router.callback_query(F.data == "settings:partner:disconnect")
async def partner_disconnect(call: CallbackQuery):
    async with async_session() as session:
        user = await _get_user(session, call.from_user.id)
        if not user:
            return
        lang = user.language
        user.partner_id = None
        user.partner_notify = False
        await session.commit()

    await call.message.edit_text(t(lang, "partner_disconnected"), reply_markup=partner_keyboard(lang, has_partner=False))
    await call.answer()


@router.callback_query(F.data.startswith("partner:confirm:"))
async def partner_confirm(call: CallbackQuery):
    code = call.data.split(":", 2)[2]
    async with async_session() as session:
        invite = (await session.execute(
            select(PartnerInvite).where(PartnerInvite.code == code)
        )).scalar_one_or_none()

        if not invite or invite.expires_at < datetime.utcnow():
            await call.answer(t("uz", "partner_code_not_found"), show_alert=True)
            return

        woman = await _get_user(session, invite.user_id)
        if not woman:
            return
        w_lang = woman.language

        man = await _get_user(session, call.from_user.id)
        m_lang = man.language if man else "uz"

        woman.partner_id = call.from_user.id
        woman.partner_notify = True
        if man:
            man.role = "partner"
        await session.execute(delete(PartnerInvite).where(PartnerInvite.code == code))
        await session.commit()

    await call.message.edit_text(t(w_lang, "partner_connected_woman"))
    await call.answer()

    try:
        await call.bot.send_message(call.from_user.id, t(m_lang, "partner_connected_man"))
    except Exception:
        pass


@router.callback_query(F.data.startswith("partner:reject:"))
async def partner_reject(call: CallbackQuery):
    code = call.data.split(":", 2)[2]
    async with async_session() as session:
        await session.execute(delete(PartnerInvite).where(PartnerInvite.code == code))
        await session.commit()

        user = await _get_user(session, call.from_user.id)
        lang = user.language if user else "uz"

    await call.message.edit_text(t(lang, "partner_rejected"))
    await call.answer()


@router.message(F.text.regexp(r"(?i)^[A-F0-9]{6}$"))
async def connect_code(message: Message):
    code = message.text.strip().upper()

    async with async_session() as session:
        # Ensure sender is registered
        man = await _get_user(session, message.from_user.id)
        if not man:
            new_user = User(id=message.from_user.id, role="partner")
            session.add(new_user)
            await session.commit()
            man = new_user
        m_lang = man.language

        if man.partner_id is not None:
            await message.answer(t(m_lang, "partner_already_connected"))
            return

        invite = (await session.execute(
            select(PartnerInvite).where(PartnerInvite.code == code)
        )).scalar_one_or_none()

        if not invite or invite.expires_at < datetime.utcnow():
            await message.answer(t(m_lang, "partner_code_not_found"))
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
            reply_markup=partner_confirm_keyboard(w_lang, code),
        )
    except Exception:
        await message.answer(t(m_lang, "error"))
        return

    await message.answer("✅")
