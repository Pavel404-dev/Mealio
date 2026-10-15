"""Recovery credentials must not survive a committed change of their owner's email."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.models.auth_session import AuthSession
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.repositories.email_otp_challenges import EmailOtpChallengesRepository
from app.repositories.password_reset_tokens import PasswordResetTokensRepository
from app.services.email_otp_challenges import EmailOtpChallengeService
from tests.test_auth_password_reset_confirm_api import (
    INVALID_RESET_DETAIL,
    NEW_PASSWORD,
    _login,
    _register_user,
)
from tests.test_auth_password_reset_otp_confirm_api import (
    INVALID_DETAIL,
    LINK_CONFIRM_URL,
    LINK_REQUEST_URL,
    ME_URL,
    OTP_CONFIRM_URL,
    OTP_REQUEST_URL,
    REFRESH_URL,
    FakePasswordResetMailer,
    FakePasswordResetOtpMailer,
    _use_mailers,
)

OLD_EMAIL = "recovery-old@example.com"
NEW_EMAIL = "recovery-new@example.com"
OLD_CODE = "001234"
FRESH_CODE = "009876"


@pytest.fixture
def recovery_mailers(monkeypatch):
    links = FakePasswordResetMailer()
    codes = FakePasswordResetOtpMailer()
    _use_mailers(codes, links)
    monkeypatch.setattr(
        "app.services.email_otp_challenges.generate_email_otp_code", lambda: OLD_CODE
    )
    return links, codes


async def _issue(client, mailers, email):
    links, codes = mailers
    for url, mailer in ((LINK_REQUEST_URL, links), (OTP_REQUEST_URL, codes)):
        count = len(mailer.calls)
        response = await client.post(url, json={"email": email})
        assert response.status_code == 202
        assert len(mailer.calls) == count + 1
        assert mailer.calls[-1][0] == email
    return links.calls[-1][1], codes.calls[-1][1]


async def _account(client, mailers, email=OLD_EMAIL, *, issue=True):
    user = await _register_user(client, email=email)
    login = await _login(client, email=email)
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    token, code = await _issue(client, mailers, email) if issue else (None, None)
    return uuid.UUID(user["id"]), headers, login, token, code


async def _snapshot(maker, user_id):
    # A new session for every observation: never assert against a cached ORM object.
    async with maker() as db:
        state = {}
        for model in (
            User,
            PasswordResetToken,
            EmailOtpChallenge,
            EmailVerificationToken,
            AuthSession,
        ):
            owner = model.id if model is User else model.user_id
            rows = await db.execute(
                select(*model.__table__.columns)
                .where(owner == user_id)
                .order_by(model.id)
            )
            state[model.__tablename__] = [dict(row) for row in rows.mappings()]
        return state


def _confirmation(kind, email, token, code):
    if kind == "link":
        return LINK_CONFIRM_URL, {"token": token, "new_password": NEW_PASSWORD}
    return OTP_CONFIRM_URL, {
        "email": email,
        "code": code,
        "new_password": NEW_PASSWORD,
    }


async def _confirm(client, kind, email, token, code, *, expected):
    url, body = _confirmation(kind, email, token, code)
    response = await client.post(url, json=body)
    assert response.status_code == expected
    if expected == 400:
        detail = INVALID_RESET_DETAIL if kind == "link" else INVALID_DETAIL
        assert response.json() == {"detail": detail}
    else:
        assert response.content == b""


async def _change(client, headers, email):
    response = await client.patch(ME_URL, headers=headers, json={"email": email})
    assert response.status_code == 200
    assert response.json()["email"] == email.strip().lower()
    assert response.json()["email_verified"] is False
    return response


def _assert_all_revoked(state):
    stamps = set()
    for table in (
        "password_reset_tokens",
        "email_otp_challenges",
        "email_verification_tokens",
    ):
        assert state[table]
        for row in state[table]:
            assert row["used_at"] is None
            assert row["revoked_at"] is not None
            stamps.add(row["revoked_at"])
    assert len(stamps) == 1  # One logical email-change timestamp for all cleanup.


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
@pytest.mark.parametrize("round_trip", [False, True])
async def test_old_recovery_rejected_after_email_change(
    client, async_session_maker, recovery_mailers, kind, round_trip
):
    user_id, headers, _, token, code = await _account(client, recovery_mailers)
    before = await _snapshot(async_session_maker, user_id)
    await _change(client, headers, NEW_EMAIL)
    changed = await _snapshot(async_session_maker, user_id)
    if round_trip:
        await _change(client, headers, OLD_EMAIL)
    current = await _snapshot(async_session_maker, user_id)
    # For OTP, round_trip=True exercises a present email and the original challenge.
    await _confirm(client, kind, OLD_EMAIL, token, code, expected=400)
    assert await _snapshot(async_session_maker, user_id) == current
    _assert_all_revoked(changed)
    _assert_all_revoked(current)
    assert current["users"][0]["password_hash"] == before["users"][0]["password_hash"]
    assert current["auth_sessions"] == before["auth_sessions"]
    await _login(client, email=OLD_EMAIL if round_trip else NEW_EMAIL)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
async def test_fresh_recovery_at_new_email_works(
    client, async_session_maker, recovery_mailers, monkeypatch, kind
):
    user_id, headers, login, old_token, old_code = await _account(
        client, recovery_mailers
    )
    await _change(client, headers, NEW_EMAIL)
    _assert_all_revoked(await _snapshot(async_session_maker, user_id))
    monkeypatch.setattr(
        "app.services.email_otp_challenges.generate_email_otp_code", lambda: FRESH_CODE
    )
    token, code = await _issue(client, recovery_mailers, NEW_EMAIL)
    assert token != old_token
    assert code == FRESH_CODE != old_code
    await _confirm(client, kind, NEW_EMAIL, token, code, expected=204)
    state = await _snapshot(async_session_maker, user_id)
    assert all(row["revoked_at"] for row in state["auth_sessions"])
    assert verify_password(NEW_PASSWORD, state["users"][0]["password_hash"])
    await _confirm(client, kind, NEW_EMAIL, token, code, expected=400)
    await _confirm(client, "link", OLD_EMAIL, old_token, old_code, expected=400)
    refresh = await client.post(
        REFRESH_URL, json={"refresh_token": login["refresh_token"]}
    )
    assert refresh.status_code == 401
    await _login(client, email=NEW_EMAIL, password=NEW_PASSWORD)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
@pytest.mark.parametrize("change", ["same_email", "full_name", "duplicate", "invalid"])
async def test_non_email_change_preserves_recovery(
    client, async_session_maker, recovery_mailers, kind, change
):
    user_id, headers, _, token, code = await _account(client, recovery_mailers)
    foreign_id, _, _, _, _ = await _account(client, recovery_mailers, NEW_EMAIL)
    before = await _snapshot(async_session_maker, user_id)
    foreign = await _snapshot(async_session_maker, foreign_id)
    payload, status = {
        "same_email": ({"email": f"  {OLD_EMAIL.upper()}  "}, 200),
        "full_name": ({"full_name": "Updated Name"}, 200),
        "duplicate": ({"email": NEW_EMAIL}, 409),
        "invalid": ({"email": "invalid-address"}, 422),
    }[change]
    response = await client.patch(ME_URL, headers=headers, json=payload)
    assert response.status_code == status
    after = await _snapshot(async_session_maker, user_id)
    if change == "full_name":
        before["users"][0]["full_name"] = "Updated Name"
        assert after["users"][0]["updated_at"] >= before["users"][0]["updated_at"]
        before["users"][0]["updated_at"] = after["users"][0]["updated_at"]
    assert after == before
    await _confirm(client, kind, OLD_EMAIL, token, code, expected=204)
    assert await _snapshot(async_session_maker, foreign_id) == foreign


@pytest.mark.asyncio
async def test_email_change_revokes_all_targets_preserving_history_and_other_owner(
    client, async_session_maker, recovery_mailers
):
    user_id, headers, _, _, _ = await _account(client, recovery_mailers)
    foreign_id, _, _, token, code = await _account(
        client, recovery_mailers, "foreign@example.com"
    )
    async with async_session_maker() as db:
        service = EmailOtpChallengeService(db)
        for purpose in EmailOtpPurpose:
            await service.issue_challenge(
                user_id=user_id, purpose=purpose, target_email="former@example.com"
            )
        # Used and revoked history must survive exactly; expired unused rows are revoked.
        now = datetime.now(UTC) - timedelta(days=1)
        for state in ("used_at", "revoked_at", "expired"):
            attrs = {state: now} if state != "expired" else {}
            db.add(
                PasswordResetToken(
                    user_id=user_id, token_hash=(state[0] * 64), expires_at=now, **attrs
                )
            )
            db.add(
                EmailOtpChallenge(
                    user_id=user_id,
                    purpose=EmailOtpPurpose.PASSWORD_RESET,
                    target_email=f"{state}@example.com",
                    code_digest="a" * 64,
                    expires_at=now,
                    last_sent_at=now,
                    send_count=1,
                    failed_attempts=2,
                    **attrs,
                )
            )
        await db.commit()
    before = await _snapshot(async_session_maker, user_id)
    foreign = await _snapshot(async_session_maker, foreign_id)
    await _change(client, headers, NEW_EMAIL)
    after = await _snapshot(async_session_maker, user_id)
    for table in (
        "password_reset_tokens",
        "email_otp_challenges",
        "email_verification_tokens",
    ):
        for old, new in zip(before[table], after[table], strict=True):
            assert old["id"] == new["id"]
            if old["used_at"] or old["revoked_at"]:
                assert new == old
            else:
                assert new["used_at"] is None
                assert new["revoked_at"] is not None
                if table == "email_otp_challenges":
                    assert new["failed_attempts"] == old["failed_attempts"]
    assert await _snapshot(async_session_maker, foreign_id) == foreign
    await _confirm(client, "otp", "foreign@example.com", token, code, expected=204)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["link", "otp"])
@pytest.mark.parametrize("kind", ["link", "otp"])
async def test_cleanup_sql_failure_rolls_back_everything(
    client, async_session_maker, recovery_mailers, monkeypatch, failure, kind
):
    user_id, headers, _, token, code = await _account(client, recovery_mailers)
    foreign_id, _, _, _, _ = await _account(
        client, recovery_mailers, "foreign@example.com"
    )
    async with async_session_maker() as db:
        await EmailOtpChallengeService(db).issue_challenge(
            user_id=user_id,
            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
            target_email=OLD_EMAIL,
        )
        user = await db.get(User, user_id)
        user.email_verified_at = datetime.now(UTC)
        challenge = await db.scalar(
            select(EmailOtpChallenge).where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == EmailOtpPurpose.PASSWORD_RESET,
            )
        )
        challenge.failed_attempts = 1
        await db.commit()
    before = await _snapshot(async_session_maker, user_id)
    foreign = await _snapshot(async_session_maker, foreign_id)
    repository = (
        PasswordResetTokensRepository
        if failure == "link"
        else EmailOtpChallengesRepository
    )
    original = repository.revoke_unused_for_user
    executed = False

    async def fail_after_sql(self, **kwargs):
        nonlocal executed
        await original(self, **kwargs)
        if failure == "otp" and kwargs["purpose"] != EmailOtpPurpose.PASSWORD_RESET:
            return
        executed = True
        # Observe actual SQL effects inside this transaction before injecting failure.
        link = await self.db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )
        assert link.revoked_at is not None
        if failure == "otp":
            rows = (
                await self.db.scalars(
                    select(EmailOtpChallenge).where(
                        EmailOtpChallenge.user_id == user_id
                    )
                )
            ).all()
            assert rows and all(row.revoked_at for row in rows)
        raise RuntimeError("synthetic F2 cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr(repository, "revoke_unused_for_user", fail_after_sql)
        with pytest.raises(RuntimeError, match="synthetic F2 cleanup failure"):
            await client.patch(ME_URL, headers=headers, json={"email": NEW_EMAIL})
    assert executed
    assert await _snapshot(async_session_maker, user_id) == before
    assert await _snapshot(async_session_maker, foreign_id) == foreign
    await _confirm(client, kind, OLD_EMAIL, token, code, expected=204)
    await _login(client, password=NEW_PASSWORD, email=OLD_EMAIL)
