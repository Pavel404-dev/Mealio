import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.security import hash_email_otp_code
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.user import User
from app.services.email_otp_challenges import (
    EmailOtpChallengeService,
    EmailOtpConfigurationError,
    EmailOtpDeliveryLimitError,
    EmailOtpResendCooldownError,
)

DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/mealio_test"
JWT_SECRET = "test-jwt-secret-key-with-at-least-32-characters"
OTP_PEPPER = "test-email-otp-pepper-with-at-least-32-characters"
ABUSE_PEPPER = "test-auth-abuse-pepper-with-at-least-32-characters"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": DATABASE_URL,
        "jwt_secret_key": JWT_SECRET,
        "auth_abuse_pepper": ABUSE_PEPPER,
        "email_otp_pepper": OTP_PEPPER,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


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


def _different_code(code: str, *, alternate: str = "000000") -> str:
    if code != alternate:
        return alternate
    return "000001" if code != "000001" else "000002"


async def _age_latest_delivery(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    seconds: int = 120,
) -> None:
    async with db_session.begin():
        result = await db_session.execute(
            select(EmailOtpChallenge)
            .where(EmailOtpChallenge.user_id == user_id)
            .order_by(
                EmailOtpChallenge.created_at.desc(),
                EmailOtpChallenge.id.desc(),
            )
            .limit(1)
        )
        challenge = result.scalar_one()
        challenge.last_sent_at = datetime.now(UTC) - timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_issue_challenge_persists_only_digest(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-service@example.com")
    settings = _settings()
    service = EmailOtpChallengeService(db_session, settings=settings)

    delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="  OTP-Service@Example.COM ",
    )
    raw_code = delivery.code.get_secret_value()

    result = await db_session.execute(
        select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user_id)
    )
    challenge = result.scalar_one()

    assert delivery.recipient_email == "otp-service@example.com"
    assert len(raw_code) == 6
    assert raw_code.isascii()
    assert raw_code.isdigit()
    assert challenge.code_digest != raw_code
    assert challenge.code_digest == hash_email_otp_code(
        code=raw_code,
        otp_pepper=OTP_PEPPER,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION.value,
        user_id=str(user_id),
        target_email="otp-service@example.com",
    )
    assert challenge.send_count == 1
    assert challenge.failed_attempts == 0
    assert challenge.used_at is None
    assert challenge.revoked_at is None


@pytest.mark.asyncio
async def test_issue_challenge_requires_configured_pepper(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-no-pepper@example.com")
    service = EmailOtpChallengeService(
        db_session,
        settings=_settings(email_otp_pepper=None),
    )

    with pytest.raises(
        EmailOtpConfigurationError,
        match="pepper is not configured",
    ):
        await service.issue_challenge(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="otp-no-pepper@example.com",
        )


@pytest.mark.asyncio
async def test_resend_revokes_previous_code_and_increments_send_count(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-resend@example.com")
    settings = _settings(email_otp_resend_cooldown_seconds=1)
    service = EmailOtpChallengeService(db_session, settings=settings)

    first = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-resend@example.com",
    )
    await _age_latest_delivery(db_session, user_id=user_id)
    second = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-resend@example.com",
    )

    first_digest = hash_email_otp_code(
        code=first.code.get_secret_value(),
        otp_pepper=OTP_PEPPER,
        purpose=EmailOtpPurpose.PASSWORD_RESET.value,
        user_id=str(user_id),
        target_email="otp-resend@example.com",
    )
    second_digest = hash_email_otp_code(
        code=second.code.get_secret_value(),
        otp_pepper=OTP_PEPPER,
        purpose=EmailOtpPurpose.PASSWORD_RESET.value,
        user_id=str(user_id),
        target_email="otp-resend@example.com",
    )
    first_still_works = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-resend@example.com",
        code=first.code,
    )
    assert first_still_works is False

    result = await db_session.execute(
        select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user_id)
    )
    challenges = {item.code_digest: item for item in result.scalars()}

    assert challenges[first_digest].revoked_at is not None
    assert challenges[second_digest].revoked_at is None
    assert challenges[second_digest].send_count == 2


@pytest.mark.asyncio
async def test_resend_cooldown_is_enforced(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-cooldown@example.com")
    service = EmailOtpChallengeService(db_session, settings=_settings())

    await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-cooldown@example.com",
    )

    with pytest.raises(EmailOtpResendCooldownError):
        await service.issue_challenge(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="otp-cooldown@example.com",
        )


@pytest.mark.asyncio
async def test_delivery_limit_is_enforced_within_active_window(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-limit@example.com")
    settings = _settings(
        email_otp_resend_cooldown_seconds=1,
        email_otp_max_deliveries_per_window=2,
    )
    service = EmailOtpChallengeService(db_session, settings=settings)

    await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-limit@example.com",
    )
    await _age_latest_delivery(db_session, user_id=user_id)
    await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-limit@example.com",
    )
    await _age_latest_delivery(db_session, user_id=user_id)

    with pytest.raises(EmailOtpDeliveryLimitError):
        await service.issue_challenge(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email="otp-limit@example.com",
        )


@pytest.mark.asyncio
async def test_wrong_code_increments_attempts_and_exhausts_challenge(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-wrong@example.com")
    settings = _settings(email_otp_max_attempts=2)
    service = EmailOtpChallengeService(db_session, settings=settings)

    delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-wrong@example.com",
    )

    raw_code = delivery.code.get_secret_value()
    first_wrong_code = _different_code(raw_code)
    second_wrong_code = _different_code(raw_code, alternate="999999")

    first = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-wrong@example.com",
        code=SecretStr(first_wrong_code),
    )
    second = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-wrong@example.com",
        code=SecretStr(second_wrong_code),
    )
    correct_after_limit = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-wrong@example.com",
        code=delivery.code,
    )

    result = await db_session.execute(
        select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user_id)
    )
    challenge = result.scalar_one()

    assert first is False
    assert second is False
    assert correct_after_limit is False
    assert challenge.failed_attempts == 2
    assert challenge.used_at is None


@pytest.mark.asyncio
async def test_correct_code_is_single_use(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-single-use@example.com")
    service = EmailOtpChallengeService(db_session, settings=_settings())

    delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-single-use@example.com",
    )

    first = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-single-use@example.com",
        code=delivery.code,
    )
    second = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-single-use@example.com",
        code=delivery.code,
    )

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_purpose_and_email_mismatch_are_rejected(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-binding@example.com")
    service = EmailOtpChallengeService(db_session, settings=_settings())

    delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-binding@example.com",
    )

    wrong_purpose = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="otp-binding@example.com",
        code=delivery.code,
    )
    wrong_email = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="different@example.com",
        code=delivery.code,
    )

    assert wrong_purpose is False
    assert wrong_email is False


@pytest.mark.asyncio
async def test_expired_and_revoked_challenges_are_rejected(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, email="otp-state@example.com")
    service = EmailOtpChallengeService(db_session, settings=_settings())

    expired_delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="expired-state@example.com",
    )
    revoked_delivery = await service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="revoked-state@example.com",
    )

    async with db_session.begin():
        result = await db_session.execute(
            select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user_id)
        )
        challenges = list(result.scalars())
        for challenge in challenges:
            if challenge.target_email == "expired-state@example.com":
                challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            elif challenge.target_email == "revoked-state@example.com":
                challenge.revoked_at = datetime.now(UTC)

    expired = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="expired-state@example.com",
        code=expired_delivery.code,
    )
    revoked = await service.verify_and_consume(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="revoked-state@example.com",
        code=revoked_delivery.code,
    )

    assert expired is False
    assert revoked is False


@pytest.mark.asyncio
async def test_concurrent_issue_requests_are_serialized(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with async_session_maker() as setup_session:
        user_id = await _create_user(
            setup_session,
            email="otp-concurrent-issue@example.com",
        )

    async def issue_once() -> str:
        async with async_session_maker() as session:
            service = EmailOtpChallengeService(session, settings=_settings())
            try:
                await service.issue_challenge(
                    user_id=user_id,
                    purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
                    target_email="otp-concurrent-issue@example.com",
                )
            except EmailOtpResendCooldownError:
                return "cooldown"
            return "issued"

    results = await asyncio.gather(issue_once(), issue_once())

    assert sorted(results) == ["cooldown", "issued"]

    async with async_session_maker() as check_session:
        result = await check_session.execute(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == EmailOtpPurpose.EMAIL_VERIFICATION,
            )
        )
        challenges = list(result.scalars())

    assert len(challenges) == 1


@pytest.mark.asyncio
async def test_concurrent_verification_consumes_code_only_once(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with async_session_maker() as setup_session:
        user_id = await _create_user(
            setup_session,
            email="otp-concurrent@example.com",
        )
        setup_service = EmailOtpChallengeService(
            setup_session,
            settings=_settings(),
        )
        delivery = await setup_service.issue_challenge(
            user_id=user_id,
            purpose=EmailOtpPurpose.PASSWORD_RESET,
            target_email="otp-concurrent@example.com",
        )

    async def consume_once() -> bool:
        async with async_session_maker() as session:
            service = EmailOtpChallengeService(session, settings=_settings())
            return await service.verify_and_consume(
                user_id=user_id,
                purpose=EmailOtpPurpose.PASSWORD_RESET,
                target_email="otp-concurrent@example.com",
                code=delivery.code,
            )

    results = await asyncio.gather(consume_once(), consume_once())

    assert sorted(results) == [False, True]
