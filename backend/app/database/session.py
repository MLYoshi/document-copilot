from collections.abc import AsyncIterator

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = structlog.get_logger()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        yield session
    finally:
        try:
            await session.close()
        except SQLAlchemyError as exc:
            logger.warning("session_close_failed", error=str(exc))
