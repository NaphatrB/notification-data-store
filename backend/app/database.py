import os
import time
from collections.abc import AsyncGenerator

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def wait_for_db(max_retries: int = 10, delay: float = 2.0) -> None:
    """Synchronous retry loop for DB readiness. Used by entrypoint.sh before migrations."""
    import asyncio

    async def _try_connect() -> None:
        # Parse the asyncpg connection string from DATABASE_URL
        # DATABASE_URL format: postgresql+asyncpg://user:pass@host:port/db
        dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        for attempt in range(1, max_retries + 1):
            try:
                conn = await asyncpg.connect(dsn)
                await conn.close()
                print(f"Database ready (attempt {attempt}/{max_retries})")
                return
            except (OSError, asyncpg.PostgresError) as e:
                print(f"Database not ready (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(delay)
        raise RuntimeError(f"Database not reachable after {max_retries} attempts")

    asyncio.run(_try_connect())
