import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://luna:luna@localhost:5432/lunadb")
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://your-miniapp.railway.app")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
API_SECRET = os.getenv("API_SECRET", "change-me-in-production")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-me-admin")
