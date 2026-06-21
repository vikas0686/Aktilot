"""
Shared fixtures for all backend tests.

Execution order:
  1. sys.modules patch (top of file) — prevents chromadb from connecting
  2. engine fixture — creates an in-memory SQLite DB with all tables
  3. db_session fixture — wraps engine in an AsyncSession
  4. client fixture — binds the FastAPI app to the test session via dependency override
"""

import sys
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

# ── Mock chromadb before any app module imports it ────────────────────────────
# chroma_store.py does `import chromadb` at the top and lazily creates a
# PersistentClient.  Replacing the module here ensures all attribute accesses
# (chromadb.PersistentClient, collection.add, etc.) return MagicMocks.
sys.modules["chromadb"] = MagicMock()

# ── Register all ORM models so Base.metadata knows about them ─────────────────
from db.base import Base  # noqa: E402
import db.models.project  # noqa: E402, F401
import db.models.file  # noqa: E402, F401
import db.models.agent  # noqa: E402, F401
import db.models.message  # noqa: E402, F401

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from main import app
    from db.session import get_db

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
