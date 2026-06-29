from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from bot.config import DATABASE_URL
from bot.database.models import Base

_url = (
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    if DATABASE_URL.startswith("postgresql")
    else "sqlite+aiosqlite:///./luna.db"
)
engine = create_async_engine(_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(10) DEFAULT 'woman';"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS partner_id BIGINT;"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS partner_notify BOOLEAN DEFAULT FALSE;"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);"
        ))


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
