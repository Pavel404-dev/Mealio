# ruff: noqa: E402

import os
from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is required. "
        "Example: postgresql+asyncpg://mealio_user:mealio_password@localhost:5432/mealio_test"
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test_mealio_secret_key_with_more_than_32_chars",
)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault(
    "AUTH_ABUSE_PEPPER",
    "test_auth_abuse_pepper_with_more_than_32_chars",
)
os.environ.pop("OPENAI_API_KEY", None)

from app.api.deps import (
    get_email_verification_mailer,
    get_email_verification_otp_mailer,
)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F403


class _NoOpEmailVerificationMailer:
    def send_email_verification(
        self,
        *,
        recipient_email: str,
        verification_token: SecretStr,
    ) -> None:
        return None


class _NoOpEmailVerificationOtpMailer:
    def send_email_verification_otp(
        self,
        *,
        recipient_email: str,
        verification_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        return None


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def async_session_maker(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def db_session(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def client(
    async_session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_maker() as session:
            yield session

    monkeypatch.setattr(
        get_settings(),
        "email_otp_pepper",
        SecretStr("test_email_otp_pepper_with_more_than_32_chars"),
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_email_verification_mailer] = (
        lambda: _NoOpEmailVerificationMailer()
    )
    app.dependency_overrides[get_email_verification_otp_mailer] = (
        lambda: _NoOpEmailVerificationOtpMailer()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
