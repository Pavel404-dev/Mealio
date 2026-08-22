import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.user import User
from app.repositories.email_otp_challenges import EmailOtpChallengesRepository


async def _create_user(
    db_session: AsyncSession,
    *,
    email: str,
) -> uuid.UUID:
    async with db_session.begin():
        user = User(email=email)
        db_session.add(user)
        await db_session.flush()
        user_id = user.id

    return user_id


@pytest.mark.asyncio
async def test_repository_add_normalizes_target_email(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-repo@example.com")
    repository = EmailOtpChallengesRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        challenge = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="  OTP-Repo@Example.COM ",
            code_digest="a" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        await db_session.flush()
        challenge_id = challenge.id

    stored = await db_session.get(EmailOtpChallenge, challenge_id)

    assert stored is not None
    assert stored.target_email == "otp-repo@example.com"
    assert stored.failed_attempts == 0
    assert stored.send_count == 1


@pytest.mark.asyncio
async def test_repository_revoke_is_bound_to_purpose_and_email(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-revoke@example.com")
    repository = EmailOtpChallengesRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        verification = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="otp-revoke@example.com",
            code_digest="a" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        reset = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.PASSWORD_RESET,
            target_email="otp-revoke@example.com",
            code_digest="b" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        other_email = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="other@example.com",
            code_digest="c" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        await db_session.flush()
        ids = (verification.id, reset.id, other_email.id)

    async with db_session.begin():
        await repository.revoke_unused_for_target(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="OTP-Revoke@Example.COM",
            revoked_at=now,
        )

    records = (
        await db_session.execute(
            select(EmailOtpChallenge).where(EmailOtpChallenge.id.in_(ids))
        )
    ).scalars()
    by_id = {record.id: record for record in records}

    assert by_id[ids[0]].revoked_at is not None
    assert by_id[ids[1]].revoked_at is None
    assert by_id[ids[2]].revoked_at is None


@pytest.mark.asyncio
async def test_repository_failed_attempts_stop_at_limit(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-attempts@example.com")
    repository = EmailOtpChallengesRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        challenge = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.PASSWORD_RESET,
            target_email="otp-attempts@example.com",
            code_digest="d" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        await db_session.flush()
        challenge_id = challenge.id

    async with db_session.begin():
        first = await repository.increment_failed_attempts(
            challenge_id=challenge_id,
            now=now,
            max_attempts=2,
        )
    async with db_session.begin():
        second = await repository.increment_failed_attempts(
            challenge_id=challenge_id,
            now=now,
            max_attempts=2,
        )
    async with db_session.begin():
        third = await repository.increment_failed_attempts(
            challenge_id=challenge_id,
            now=now,
            max_attempts=2,
        )

    assert first == 1
    assert second == 2
    assert third is None


@pytest.mark.asyncio
async def test_repository_consume_is_single_use(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-consume@example.com")
    repository = EmailOtpChallengesRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        challenge = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="otp-consume@example.com",
            code_digest="e" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        await db_session.flush()
        challenge_id = challenge.id

    async with db_session.begin():
        first = await repository.consume_valid(
            challenge_id=challenge_id,
            now=now,
            max_attempts=5,
        )
    async with db_session.begin():
        second = await repository.consume_valid(
            challenge_id=challenge_id,
            now=now,
            max_attempts=5,
        )

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_repository_does_not_consume_expired_or_attempt_exhausted_challenge(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-invalid@example.com")
    repository = EmailOtpChallengesRepository(db_session)
    now = datetime.now(UTC)

    async with db_session.begin():
        expired = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="expired@example.com",
            code_digest="f" * 64,
            expires_at=now - timedelta(seconds=1),
            send_count=1,
            last_sent_at=now,
        )
        exhausted = repository.add(
            user_id=user_id,
            purpose=EmailOtpPurpose.PASSWORD_RESET,
            target_email="exhausted@example.com",
            code_digest="0" * 64,
            expires_at=now + timedelta(minutes=10),
            send_count=1,
            last_sent_at=now,
        )
        exhausted.failed_attempts = 5
        await db_session.flush()
        expired_id = expired.id
        exhausted_id = exhausted.id

    async with db_session.begin():
        expired_result = await repository.consume_valid(
            challenge_id=expired_id,
            now=now,
            max_attempts=5,
        )
        exhausted_result = await repository.consume_valid(
            challenge_id=exhausted_id,
            now=now,
            max_attempts=5,
        )

    assert expired_result is False
    assert exhausted_result is False
