import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth_abuse import (
    AuthAbuseAction,
    AuthAbuseDimension,
    default_auth_abuse_policies,
)
from app.core.config import Settings
from app.models.auth_abuse_bucket import AuthAbuseBucket
from app.services.auth_abuse import (
    AuthAbuseConfigurationError,
    AuthAbuseLimitExceeded,
    AuthAbuseProtectionService,
)


DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/mealio_test"
JWT_SECRET = "test-jwt-secret-key-with-at-least-32-characters"
ABUSE_PEPPER = "test-auth-abuse-pepper-with-at-least-32-characters"


def _settings(
    *,
    login_ip_limit: int = 2,
    login_ip_window_seconds: int = 60,
) -> Settings:
    policies = default_auth_abuse_policies()
    policies = [
        policy.model_copy(
            update={
                "limit": login_ip_limit,
                "window_seconds": login_ip_window_seconds,
            }
        )
        if (
            policy.action is AuthAbuseAction.LOGIN
            and policy.dimension is AuthAbuseDimension.IP
        )
        else policy
        for policy in policies
    ]
    return Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        jwt_secret_key=JWT_SECRET,
        auth_abuse_pepper=ABUSE_PEPPER,
        auth_abuse_policies=policies,
    )


def _login_identifiers(
    *,
    ip: str = "192.0.2.10",
    email: str = "user@example.com",
) -> dict[AuthAbuseDimension, str]:
    return {
        AuthAbuseDimension.IP: ip,
        AuthAbuseDimension.EMAIL: email,
    }


@pytest.mark.asyncio
async def test_service_blocks_above_limit_and_resets_window(
    db_session: AsyncSession,
) -> None:
    settings = _settings(login_ip_limit=2, login_ip_window_seconds=60)
    service = AuthAbuseProtectionService(db_session, settings=settings)
    now = datetime.now(UTC)

    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(),
        now=now,
    )
    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(),
        now=now,
    )

    with pytest.raises(AuthAbuseLimitExceeded) as exc_info:
        await service.enforce(
            action=AuthAbuseAction.LOGIN,
            identifiers=_login_identifiers(),
            now=now,
        )

    assert exc_info.value.retry_after_seconds == 60

    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(),
        now=now + timedelta(seconds=61),
    )


@pytest.mark.asyncio
async def test_service_isolates_identifiers_and_actions(
    db_session: AsyncSession,
) -> None:
    settings = _settings(login_ip_limit=1)
    service = AuthAbuseProtectionService(db_session, settings=settings)
    now = datetime.now(UTC)

    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(ip="192.0.2.10"),
        now=now,
    )
    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(
            ip="192.0.2.11",
            email="other@example.com",
        ),
        now=now,
    )
    await service.enforce(
        action=AuthAbuseAction.REGISTER,
        identifiers=_login_identifiers(ip="192.0.2.10"),
        now=now,
    )


@pytest.mark.asyncio
async def test_service_requires_every_configured_dimension(
    db_session: AsyncSession,
) -> None:
    service = AuthAbuseProtectionService(db_session, settings=_settings())

    with pytest.raises(AuthAbuseConfigurationError, match="email"):
        await service.enforce(
            action=AuthAbuseAction.LOGIN,
            identifiers={AuthAbuseDimension.IP: "192.0.2.10"},
        )


@pytest.mark.asyncio
async def test_service_persists_only_identifier_digests(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_ip = "192.0.2.10"
    raw_email = "private-user@example.com"
    settings = _settings()
    service = AuthAbuseProtectionService(db_session, settings=settings)

    await service.enforce(
        action=AuthAbuseAction.LOGIN,
        identifiers=_login_identifiers(ip=raw_ip, email=raw_email),
    )

    result = await db_session.execute(select(AuthAbuseBucket))
    buckets = result.scalars().all()

    assert len(buckets) == 2
    assert all(len(bucket.identifier_digest) == 64 for bucket in buckets)
    assert all(raw_ip not in bucket.identifier_digest for bucket in buckets)
    assert all(raw_email not in bucket.identifier_digest for bucket in buckets)
    assert raw_ip not in caplog.text
    assert raw_email not in caplog.text
    assert ABUSE_PEPPER not in caplog.text


@pytest.mark.asyncio
async def test_service_concurrency_allows_exactly_the_limit(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(login_ip_limit=5)
    now = datetime.now(UTC)

    async def enforce_once() -> bool:
        async with async_session_maker() as session:
            service = AuthAbuseProtectionService(session, settings=settings)
            try:
                await service.enforce(
                    action=AuthAbuseAction.LOGIN,
                    identifiers=_login_identifiers(),
                    now=now,
                )
            except AuthAbuseLimitExceeded:
                return False
            return True

    allowed = await asyncio.gather(*(enforce_once() for _ in range(10)))

    assert sum(allowed) == 5
