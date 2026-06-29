from __future__ import annotations
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select

from bot.database.db import async_session
from bot.database.models import Cycle, Symptom, User
from bot.services.cycle_service import (
    get_or_create_user, get_all_cycles, get_last_cycle,
    compute_next_period, compute_ovulation, compute_pms_start,
)
from bot.api.admin_routes import router as admin_router

app = FastAPI(title="Luna Bot API")
app.include_router(admin_router)

_PANEL = os.path.join(os.path.dirname(__file__), "admin_panel.html")

@app.get("/admin/")
async def serve_admin():
    return FileResponse(_PANEL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/api/user/{user_id}/partner/disconnect")
async def disconnect_partner(user_id: int):
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.partner_id = None
            user.partner_notify = False
            await session.commit()
    return {"ok": True}


@app.get("/api/user/{user_id}/data")
async def get_user_data(user_id: int):
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        cycles = await get_all_cycles(session, user_id)
        last = await get_last_cycle(session, user_id)

        result = await session.execute(
            select(Symptom).where(Symptom.user_id == user_id).order_by(Symptom.date.desc()).limit(90)
        )
        symptoms = result.scalars().all()

    next_period = None
    ovulation = None
    pms_start = None
    if last:
        next_period = compute_next_period(last.start_date, user.avg_cycle_length)
        ovulation = compute_ovulation(next_period)
        pms_start = compute_pms_start(ovulation)

    return {
        "user": {
            "language": user.language,
            "avg_cycle_length": user.avg_cycle_length,
            "avg_period_length": user.avg_period_length,
            "partner_id": user.partner_id,
            "partner_notify": user.partner_notify,
        },
        "predictions": {
            "next_period": next_period.isoformat() if next_period else None,
            "ovulation": ovulation.isoformat() if ovulation else None,
            "pms_start": pms_start.isoformat() if pms_start else None,
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
                "mood": s.mood,
            }
            for s in symptoms
        ],
    }
