import asyncio
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.database.db import init_db, async_session
from bot.handlers import start, cycle, symptoms, settings, partner, notes
from bot.middlewares import OnboardingGuard
from bot.services.cycle_service import recalc_all_users
from bot.services.reminder import setup_scheduler
from bot.api.routes import app as fastapi_app

logging.basicConfig(level=logging.INFO)


async def run_api():
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await init_db()
    async with async_session() as session:
        await recalc_all_users(session)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(OnboardingGuard())
    dp.callback_query.outer_middleware(OnboardingGuard())

    dp.include_router(start.router)
    dp.include_router(cycle.router)
    dp.include_router(symptoms.router)
    dp.include_router(settings.router)
    dp.include_router(partner.router)
    dp.include_router(notes.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    try:
        await asyncio.gather(
            dp.start_polling(bot, allowed_updates=["message", "callback_query"]),
            run_api(),
        )
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
