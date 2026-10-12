from __future__ import annotations
import os
import time

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select

from bot.config import BOT_TOKEN
from bot.database.db import async_session
from bot.database.models import Symptom, User
from bot.services.cycle_service import get_all_cycles, get_predictions
from bot.api.admin_routes import router as admin_router

app = FastAPI(title="Luna Bot API")
app.include_router(admin_router)

_PANEL = os.path.join(os.path.dirname(__file__), "admin_panel.html")
INIT_DATA_MAX_AGE = 24 * 3600


@app.get("/admin/")
async def serve_admin():
    return FileResponse(_PANEL)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _auth_user_id(init_data: str | None) -> int:
    """Telegram signs the Mini App's initData with the bot token; trust only that."""
    if not init_data:
        raise HTTPException(401, "Missing Telegram init data")
    try:
        data = safe_parse_webapp_init_data(BOT_TOKEN, init_data)
    except ValueError:
        raise HTTPException(401, "Invalid Telegram init data")
    if time.time() - data.auth_date.timestamp() > INIT_DATA_MAX_AGE:
        raise HTTPException(401, "Telegram init data expired")
    if not data.user:
        raise HTTPException(401, "No user in init data")
    return data.user.id


@app.post("/api/me/partner/disconnect")
async def disconnect_partner(x_telegram_init_data: str | None = Header(None)):
    user_id = _auth_user_id(x_telegram_init_data)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.partner_id = None
            user.partner_notify = False
            await session.commit()
    return {"ok": True}


@app.get("/api/me/data")
async def get_user_data(x_telegram_init_data: str | None = Header(None)):
    user_id = _auth_user_id(x_telegram_init_data)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found")
        cycles = await get_all_cycles(session, user_id)
        pred = await get_predictions(session, user)
        symptoms = (await session.execute(
            select(Symptom).where(Symptom.user_id == user_id).order_by(Symptom.date.desc())
        )).scalars().all()

    return {
        "user": {
            "language": user.language,
            "avg_cycle_length": user.avg_cycle_length,
            "avg_period_length": user.avg_period_length,
            "partner_id": user.partner_id,
            "partner_notify": user.partner_notify,
        },
        "predictions": {
            "next_period": pred["next_period"].isoformat() if pred else None,
            "ovulation": pred["ovulation"].isoformat() if pred else None,
            "pms_start": pred["pms_start"].isoformat() if pred else None,
        },
        "cycles": [
            {
                "id": c.id,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "cycle_length": c.cycle_length,
            }
            for c in cycles
        ],
        "symptoms": [
            {
                "date": s.date.isoformat(),
                "flow": s.flow,
                "pain_level": s.pain_level,
                "pain_types": s.pain_types,
                "mood": s.mood,
                "notes": s.notes,
            }
            for s in symptoms
        ],
    }
