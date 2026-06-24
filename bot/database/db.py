from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import DATABASE_URL
from bot.database.models import Base

_url = DATABASE_URL if DATABASE_URL.startswith("postgresql") else "sqlite+aiosqlite:///./luna.db"
engine = create_async_engine(_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
