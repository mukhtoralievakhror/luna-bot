import re
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.db import async_session
from bot.database.models import User
from bot.handlers.partner import PARTNER_CODE
from bot.handlers.start import send_welcome

_CODE_RE = re.compile(PARTNER_CODE)
_SETUP_CALLBACKS = ("setup_lang:", "setup_role:")


class OnboardingGuard(BaseMiddleware):
    """Sends anyone who hasn't finished setup (new, or just reset) back to language choice."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state is not None and await state.get_state() is not None:
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip()
            if text.startswith("/start") or _CODE_RE.match(text):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if (event.data or "").startswith(_SETUP_CALLBACKS):
                return await handler(event, data)

        async with async_session() as session:
            user = await session.get(User, event.from_user.id)
        if user and user.onboarded:
            return await handler(event, data)

        lang = user.language if user else "uz"
        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await send_welcome(event.message, lang)
        else:
            await send_welcome(event, lang)
