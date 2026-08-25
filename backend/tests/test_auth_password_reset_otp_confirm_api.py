import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_password_reset_mailer, get_password_reset_otp_mailer
from app.main import app
from app.models.auth_session import AuthSession
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_tokens import PasswordResetTokensRepository
from app.services.email_otp_challenges import EmailOtpChallengeService

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
REFRESH_URL = "/api/v1/auth/refresh"
LINK_REQUEST_URL = "/api/v1/auth/password-reset/request"
LINK_CONFIRM_URL = "/api/v1/auth/password-reset/confirm"
OTP_REQUEST_URL = "/api/v1/auth/password-reset/otp/request"
OTP_CONFIRM_URL = "/api/v1/auth/password-reset/otp/confirm"
INVALID_DETAIL = "Invalid or expired password reset code."
OLD_PASSWORD = "Mealio-password-123"
NEW_PASSWORD = "Mealio-new-password-456"


class FakePasswordResetOtpMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime]] = []

    def send_password_reset_otp(
        self,
        *,
        recipient_email: str,
        reset_code: SecretStr,
        expires_at: datetime,
    ) -> None:
        self.calls.append(
            (
                recipient_email,
                reset_code.get_secret_value(),
                expires_at,
            )
        )


class FakePasswordResetMailer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None:
        self.calls.append((recipient_email, reset_token.get_secret_value()))


def _use_mailers(
    otp_mailer: FakePasswordResetOtpMailer,
    link_mailer: FakePasswordResetMailer | None = None,
) -> None:
    app.dependency_overrides[get_password_reset_otp_mailer] = lambda: otp_mailer
    if link_mailer is not None:
        app.dependency_overrides[get_password_reset_mailer] = lambda: link_mailer


def _assert_invalid(response) -> None:
    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_DETAIL}


async def _register_user(
    client: AsyncClient,
    *,
    email: str = "otp-reset-confirm@example.com",
    password: str = OLD_PASSWORD,
) -> dict:
    response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "OTP Reset Confirm User",
            "password": password,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _login(
    client: AsyncClient,
    *,
    email: str = "otp-reset-confirm@example.com",
    password: str = OLD_PASSWORD,
) -> dict:
    response = await client.post(
        LOGIN_URL,
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


async def _request_code(
    client: AsyncClient,
    mailer: FakePasswordResetOtpMailer,
    *,
    email: str = "otp-reset-confirm@example.com",
) -> str:
    before_calls = len(mailer.calls)
    response = await client.post(OTP_REQUEST_URL, json={"email": email})
    assert response.status_code == 202
    assert len(mailer.calls) == before_calls + 1
    return mailer.calls[-1][1]


async def _request_link_token(
    client: AsyncClient,
    mailer: FakePasswordResetMailer,
    *,
    email: str = "otp-reset-confirm@example.com",
) -> str:
    response = await client.post(LINK_REQUEST_URL, json={"email": email})
    assert response.status_code == 202
    return mailer.calls[-1][1]


@pytest.mark.asyncio
async def test_otp_reset_is_atomic_revokes_credentials_and_preserves_access_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "app.services.email_otp_challenges.generate_email_otp_code",
        lambda: "001234",
    )
    otp_mailer = FakePasswordResetOtpMailer()
    link_mailer = FakePasswordResetMailer()
    _use_mailers(otp_mailer, link_mailer)
    registered_user = await _register_user(client)
    user_id = uuid.UUID(registered_user["id"])
    old_tokens = await _login(client)

    other_email = "other-otp-reset-user@example.com"
    await _register_user(client, email=other_email)
    other_tokens = await _login(client, email=other_email)

    otp_service = EmailOtpChallengeService(db_session)
    old_email_reset_delivery = await otp_service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.PASSWORD_RESET,
        target_email="former-otp-reset@example.com",
    )
    assert old_email_reset_delivery.code.get_secret_value()
    email_verification_delivery = await otp_service.issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-reset-confirm@example.com",
    )
    assert email_verification_delivery.code.get_secret_value()

    link_token = await _request_link_token(client, link_mailer)
    code = await _request_code(client, otp_mailer)
    assert code == "001234"

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "  OTP-RESET-CONFIRM@EXAMPLE.COM  ",
            "code": code,
            "new_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert code not in response.text
    assert NEW_PASSWORD not in response.text
    assert code not in caplog.text
    assert NEW_PASSWORD not in caplog.text

    old_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": OLD_PASSWORD,
        },
    )
    new_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": NEW_PASSWORD,
        },
    )
    old_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": old_tokens["refresh_token"]},
    )
    other_refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": other_tokens["refresh_token"]},
    )
    existing_access = await client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {old_tokens['access_token']}"},
    )
    reuse = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": code,
            "new_password": "Another-password-789",
        },
    )
    old_link = await client.post(
        LINK_CONFIRM_URL,
        json={"token": link_token, "new_password": "Link-password-789"},
    )

    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert old_refresh.status_code == 401
    assert other_refresh.status_code == 200
    assert existing_access.status_code == 200
    _assert_invalid(reuse)
    assert old_link.status_code == 400

    db_session.expire_all()
    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user_id)
    )
    challenges = list(challenge_result.scalars())
    password_reset_challenge = next(
        item
        for item in challenges
        if item.purpose is EmailOtpPurpose.PASSWORD_RESET
        and item.target_email == "otp-reset-confirm@example.com"
    )
    old_email_reset_challenge = next(
        item
        for item in challenges
        if item.purpose is EmailOtpPurpose.PASSWORD_RESET
        and item.target_email == "former-otp-reset@example.com"
    )
    email_challenge = next(
        item
        for item in challenges
        if item.purpose is EmailOtpPurpose.EMAIL_VERIFICATION
    )
    assert password_reset_challenge.used_at is not None
    assert old_email_reset_challenge.used_at is None
    assert old_email_reset_challenge.revoked_at is not None
    assert email_challenge.used_at is None
    assert email_challenge.revoked_at is None


@pytest.mark.asyncio
async def test_otp_reset_preserves_password_whitespace_exactly(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_mailers(mailer)
    await _register_user(client)
    code = await _request_code(client, mailer)
    password_with_spaces = "  Mealio-password  "

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": code,
            "new_password": password_with_spaces,
        },
    )
    assert response.status_code == 204

    exact_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": password_with_spaces,
        },
    )
    trimmed_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": password_with_spaces.strip(),
        },
    )
    assert exact_login.status_code == 200
    assert trimmed_login.status_code == 401


@pytest.mark.asyncio
async def test_wrong_otp_commits_attempt_without_changing_password(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_mailers(mailer)
    registered_user = await _register_user(client)
    code = await _request_code(client, mailer)
    wrong_code = "000000" if code != "000000" else "000001"

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": wrong_code,
            "new_password": NEW_PASSWORD,
        },
    )
    _assert_invalid(response)

    old_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": OLD_PASSWORD,
        },
    )
    assert old_login.status_code == 200

    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == uuid.UUID(registered_user["id"]),
            EmailOtpChallenge.purpose == EmailOtpPurpose.PASSWORD_RESET,
        )
    )
    challenge = challenge_result.scalar_one()
    assert challenge.failed_attempts == 1
    assert challenge.used_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["expired", "used", "revoked", "exhausted"])
async def test_otp_reset_returns_same_error_for_all_inactive_states(
    client: AsyncClient,
    db_session: AsyncSession,
    state: str,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_mailers(mailer)
    registered_user = await _register_user(client)
    code = await _request_code(client, mailer)

    async with db_session.begin():
        challenge_result = await db_session.execute(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.user_id == uuid.UUID(registered_user["id"]),
                EmailOtpChallenge.purpose == EmailOtpPurpose.PASSWORD_RESET,
            )
        )
        challenge = challenge_result.scalar_one()
        if state == "expired":
            challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif state == "used":
            challenge.used_at = datetime.now(UTC)
        elif state == "revoked":
            challenge.revoked_at = datetime.now(UTC)
        else:
            challenge.failed_attempts = 5

    response = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": code,
            "new_password": NEW_PASSWORD,
        },
    )
    _assert_invalid(response)


@pytest.mark.asyncio
async def test_otp_reset_rejects_unknown_email_and_email_verification_purpose(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    unknown = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "unknown-otp-reset@example.com",
            "code": "123456",
            "new_password": NEW_PASSWORD,
        },
    )
    _assert_invalid(unknown)

    registered_user = await _register_user(client)
    user_id = uuid.UUID(registered_user["id"])
    delivery = await EmailOtpChallengeService(db_session).issue_challenge(
        user_id=user_id,
        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
        target_email="otp-reset-confirm@example.com",
    )

    wrong_purpose = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": delivery.code.get_secret_value(),
            "new_password": NEW_PASSWORD,
        },
    )
    _assert_invalid(wrong_purpose)


@pytest.mark.asyncio
async def test_otp_reset_attempt_limit_rejects_correct_code_after_exhaustion(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_mailers(mailer)
    await _register_user(client)
    code = await _request_code(client, mailer)
    wrong_code = "999999" if code != "999999" else "999998"

    for _ in range(5):
        response = await client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-reset-confirm@example.com",
                "code": wrong_code,
                "new_password": NEW_PASSWORD,
            },
        )
        _assert_invalid(response)

    correct_after_limit = await client.post(
        OTP_CONFIRM_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "code": code,
            "new_password": NEW_PASSWORD,
        },
    )
    _assert_invalid(correct_after_limit)


@pytest.mark.asyncio
async def test_otp_reset_rolls_back_every_change_when_revocation_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    otp_mailer = FakePasswordResetOtpMailer()
    link_mailer = FakePasswordResetMailer()
    _use_mailers(otp_mailer, link_mailer)
    registered_user = await _register_user(client)
    user_id = uuid.UUID(registered_user["id"])
    login_tokens = await _login(client)
    link_token = await _request_link_token(client, link_mailer)
    code = await _request_code(client, otp_mailer)

    async def fail_link_revocation(
        self: PasswordResetTokensRepository,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        raise RuntimeError("simulated link reset revocation failure")

    monkeypatch.setattr(
        PasswordResetTokensRepository,
        "revoke_unused_for_user",
        fail_link_revocation,
    )

    with pytest.raises(RuntimeError, match="simulated link reset revocation failure"):
        await client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-reset-confirm@example.com",
                "code": code,
                "new_password": NEW_PASSWORD,
            },
        )

    old_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": OLD_PASSWORD,
        },
    )
    new_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": NEW_PASSWORD,
        },
    )
    refresh = await client.post(
        REFRESH_URL,
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert old_login.status_code == 200
    assert new_login.status_code == 401
    assert refresh.status_code == 200

    db_session.expire_all()
    challenge_result = await db_session.execute(
        select(EmailOtpChallenge).where(
            EmailOtpChallenge.user_id == user_id,
            EmailOtpChallenge.purpose == EmailOtpPurpose.PASSWORD_RESET,
        )
    )
    challenge = challenge_result.scalar_one()
    assert challenge.used_at is None
    assert challenge.revoked_at is None

    link_result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    link_record = link_result.scalar_one()
    assert link_record.used_at is None
    assert link_record.revoked_at is None

    session_result = await db_session.execute(
        select(AuthSession).where(AuthSession.user_id == user_id)
    )
    sessions = list(session_result.scalars())
    assert sessions
    assert all(session.revoked_at is None for session in sessions)
    assert link_token


@pytest.mark.asyncio
async def test_concurrent_otp_reset_confirm_allows_exactly_one_success(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetOtpMailer()
    _use_mailers(mailer)
    await _register_user(client)
    code = await _request_code(client, mailer)
    first_password = "Concurrent-password-111"
    second_password = "Concurrent-password-222"

    first_response, second_response = await asyncio.gather(
        client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-reset-confirm@example.com",
                "code": code,
                "new_password": first_password,
            },
        ),
        client.post(
            OTP_CONFIRM_URL,
            json={
                "email": "otp-reset-confirm@example.com",
                "code": code,
                "new_password": second_password,
            },
        ),
    )

    assert sorted([first_response.status_code, second_response.status_code]) == [
        204,
        400,
    ]

    first_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": first_password,
        },
    )
    second_login = await client.post(
        LOGIN_URL,
        json={
            "email": "otp-reset-confirm@example.com",
            "password": second_password,
        },
    )
    assert sorted([first_login.status_code, second_login.status_code]) == [200, 401]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": None, "code": "123456", "new_password": NEW_PASSWORD},
        {
            "email": "otp-reset-confirm@example.com",
            "code": None,
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "12345",
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "1234567",
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "12a456",
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "123 56",
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "１２３４５６",
            "new_password": NEW_PASSWORD,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "123456",
            "new_password": "private-short",
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "123456",
            "new_password": " " * 15,
        },
        {
            "email": "otp-reset-confirm@example.com",
            "code": "123456",
            "new_password": "x" * 129,
        },
    ],
)
async def test_otp_reset_confirm_rejects_invalid_payload_without_echoing_secrets(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(OTP_CONFIRM_URL, json=payload)

    assert response.status_code == 422
    if isinstance(payload.get("code"), str):
        assert payload["code"] not in response.text
    if isinstance(payload.get("new_password"), str):
        assert payload["new_password"] not in response.text
