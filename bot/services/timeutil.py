from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def today() -> date:
    return datetime.now(TZ).date()
