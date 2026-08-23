import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth_abuse import AuthAbuseAction, AuthAbuseDimension
from app.models.auth_abuse_bucket import AuthAbuseBucket
from app.repositories.auth_abuse_buckets import AuthAbuseBucketsRepository


@pytest.mark.asyncio
async def test_consume_increments_and_caps_active_bucket(
    db_session: AsyncSession,
) -> None:
    repository = AuthAbuseBucketsRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        counts = [
            (
                await repository.consume(
                    action=AuthAbuseAction.LOGIN,
                    dimension=AuthAbuseDimension.IP,
                    identifier_digest="a" * 64,
                    limit=2,
                    window_seconds=60,
                    now=now,
                )
            ).request_count
            for _ in range(4)
        ]

    assert counts == [1, 2, 3, 3]


@pytest.mark.asyncio
async def test_consume_resets_expired_bucket(
    db_session: AsyncSession,
) -> None:
    repository = AuthAbuseBucketsRepository(db_session)
    started_at = datetime.now(UTC)

    async with db_session.begin():
        first = await repository.consume(
            action=AuthAbuseAction.LOGIN,
            dimension=AuthAbuseDimension.EMAIL,
            identifier_digest="b" * 64,
            limit=2,
            window_seconds=60,
            now=started_at,
        )
        reset = await repository.consume(
            action=AuthAbuseAction.LOGIN,
            dimension=AuthAbuseDimension.EMAIL,
            identifier_digest="b" * 64,
            limit=2,
            window_seconds=60,
            now=started_at + timedelta(seconds=61),
        )

    assert first.request_count == 1
    assert reset.request_count == 1
    assert reset.expires_at == started_at + timedelta(seconds=121)


@pytest.mark.asyncio
async def test_actions_dimensions_and_identifiers_are_isolated(
    db_session: AsyncSession,
) -> None:
    repository = AuthAbuseBucketsRepository(db_session)
    now = datetime.now(UTC)
    cases = [
        (AuthAbuseAction.LOGIN, AuthAbuseDimension.IP, "c" * 64),
        (AuthAbuseAction.REGISTER, AuthAbuseDimension.IP, "c" * 64),
        (AuthAbuseAction.LOGIN, AuthAbuseDimension.EMAIL, "c" * 64),
        (AuthAbuseAction.LOGIN, AuthAbuseDimension.IP, "d" * 64),
    ]

    async with db_session.begin():
        results = [
            await repository.consume(
                action=action,
                dimension=dimension,
                identifier_digest=digest,
                limit=5,
                window_seconds=60,
                now=now,
            )
            for action, dimension, digest in cases
        ]

    assert [result.request_count for result in results] == [1, 1, 1, 1]


@pytest.mark.asyncio
async def test_delete_expired_is_bounded(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    for index in range(3):
        db_session.add(
            AuthAbuseBucket(
                action=AuthAbuseAction.LOGIN,
                dimension=AuthAbuseDimension.EMAIL,
                identifier_digest=f"{index:064x}",
                request_count=1,
                window_started_at=now - timedelta(minutes=2),
                expires_at=now - timedelta(minutes=1),
            )
        )
    await db_session.commit()

    repository = AuthAbuseBucketsRepository(db_session)
    async with db_session.begin():
        deleted = await repository.delete_expired(now=now, batch_size=2)

    remaining = await db_session.scalar(select(func.count(AuthAbuseBucket.id)))

    assert deleted == 2
    assert remaining == 1


@pytest.mark.asyncio
async def test_concurrent_consume_cannot_bypass_limit(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)

    async def consume_once() -> bool:
        async with async_session_maker() as session:
            repository = AuthAbuseBucketsRepository(session)
            async with session.begin():
                result = await repository.consume(
                    action=AuthAbuseAction.LOGIN,
                    dimension=AuthAbuseDimension.IP,
                    identifier_digest="e" * 64,
                    limit=5,
                    window_seconds=60,
                    now=now,
                )
            return result.request_count <= 5

    allowed = await asyncio.gather(*(consume_once() for _ in range(10)))

    assert sum(allowed) == 5

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuthAbuseBucket).where(
                AuthAbuseBucket.action == AuthAbuseAction.LOGIN,
                AuthAbuseBucket.dimension == AuthAbuseDimension.IP,
                AuthAbuseBucket.identifier_digest == "e" * 64,
            )
        )
        bucket = result.scalar_one()

    assert bucket.request_count == 6
