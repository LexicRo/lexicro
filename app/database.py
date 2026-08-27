import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def database_ok(timeout: float = 2.0) -> bool:
    """A bounded `SELECT 1`. True if the database answered, False otherwise.

    Deliberately narrow. It proves the connection pool can reach Postgres,
    which is the gap OQ-022 part 3 identified: every keyed request reads
    `api_keys` through the rate limiter, so an unreachable database means the
    API is dead for all authenticated traffic while /health says 200. It does
    NOT prove any particular table is readable, and it is not a substitute
    for exercising a real query path.

    Two guarantees, both load-bearing for the caller:

    * **It never raises.** An exception escaping here becomes a framework 500
      with no body and no version -- strictly less useful than the 503 the
      endpoint exists to serve. The database being broken is the case this is
      for, so it must not be the case that breaks it.
    * **It is bounded.** A hung database must not become a hung health
      endpoint. Without the timeout this would be worse than the defect it
      replaces: `probe_api.sh`'s own `-m 15` would eventually fire, but the
      container healthcheck and any human curl would sit there, and an
      endpoint that hangs lies by omission.

    `CancelledError` is BaseException and is deliberately NOT caught -- a real
    cancellation is the caller going away, not a database fault.
    """
    async def probe() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(probe(), timeout=timeout)
        return True
    except Exception:
        return False
