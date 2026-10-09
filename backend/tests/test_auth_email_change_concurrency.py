"""Deterministic PostgreSQL interleavings at the authentication/owner-lock boundary."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User
from app.repositories.email_otp_challenges import EmailOtpChallengesRepository
from app.repositories.users import UsersRepository
from app.services.users import UsersService
from tests.test_auth_email_verification_email_change_api import (
    CONFIRM_VERIFICATION_URL,
    INVALID_DETAIL,
    ME_URL,
    OTP_CONFIRM_URL,
    OTP_INVALID_DETAIL,
    OTP_REQUEST_URL,
    FakeEmailVerificationMailer,
    FakeEmailVerificationOtpMailer,
    _register_and_login,
    _use_fake_mailer,
    _use_fake_otp_mailer,
)


async def _account(client: AsyncClient, email: str) -> tuple:
    links = FakeEmailVerificationMailer()
    codes = FakeEmailVerificationOtpMailer()
    _use_fake_mailer(links)
    _use_fake_otp_mailer(codes)
    user, token, headers = await _register_and_login(client, links, email=email)
    response = await client.post(OTP_REQUEST_URL, json={"email": email})
    assert response.status_code == 202
    assert len(codes.calls) == 1
    return uuid.UUID(user["id"]), headers, token, codes.calls[0][1]


def _confirmation(kind: str, email: str, token: str, code: str) -> tuple:
    if kind == "link":
        return CONFIRM_VERIFICATION_URL, {"token": token}, INVALID_DETAIL
    return OTP_CONFIRM_URL, {"email": email, "code": code}, OTP_INVALID_DETAIL


async def _snapshot(maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID):
    # Independent reads also catch stale response/identity-map assertions.
    async with maker() as db:
        user = await db.get(User, user_id)
        links = (
            await db.execute(
                select(
                    EmailVerificationToken.id,
                    EmailVerificationToken.used_at,
                    EmailVerificationToken.revoked_at,
                )
                .where(EmailVerificationToken.user_id == user_id)
                .order_by(EmailVerificationToken.id)
            )
        ).all()
        codes = (
            await db.execute(
                select(
                    EmailOtpChallenge.id,
                    EmailOtpChallenge.used_at,
                    EmailOtpChallenge.revoked_at,
                    EmailOtpChallenge.failed_attempts,
                    EmailOtpChallenge.updated_at,
                )
                .where(EmailOtpChallenge.user_id == user_id)
                .order_by(EmailOtpChallenge.id)
            )
        ).all()
        assert user is not None
        return (user.email, user.email_verified_at, user.full_name), links, codes


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
@pytest.mark.parametrize("change", ["email", "same_email", "full_name"])
async def test_confirmation_commits_after_authentication_before_patch_lock(
    client,
    async_session_maker,
    monkeypatch,
    kind,
    change,
):
    email = "concurrent-old@example.com"
    user_id, headers, token, code = await _account(client, email)
    foreign_id, _, _, _ = await _account(client, "foreign@example.com")
    foreign_before = await _snapshot(async_session_maker, foreign_id)
    authenticated = asyncio.Event()
    release = asyncio.Event()
    update = UsersService.update_user
    patch_session = None

    async def pause_after_authentication(self, user_id, data):
        nonlocal patch_session
        patch_session = self.db
        # Retain the actual object loaded by get_current_user, without another SELECT.
        cached = self.db.identity_map[
            User.__mapper__.identity_key_from_primary_key((user_id,))
        ]
        assert cached.email == email
        assert cached.email_verified_at is None
        assert not self.db.dirty
        authenticated.set()
        await asyncio.wait_for(release.wait(), 10)
        return await update(self, user_id, data)

    lock_name = "get_by_id_for_update" if kind == "link" else "get_by_email_for_update"
    lock = getattr(UsersRepository, lock_name)

    async def confirm_lock(self, target):
        if not release.is_set():
            assert self.db is not patch_session
        return await lock(self, target)

    monkeypatch.setattr(UsersService, "update_user", pause_after_authentication)
    monkeypatch.setattr(UsersRepository, lock_name, confirm_lock)
    payload = {
        "email": {"email": "concurrent-new@example.com"},
        "same_email": {"email": f"  {email.upper()}  "},
        "full_name": {"full_name": "Updated Name"},
    }[change]
    url, body, detail = _confirmation(kind, email, token, code)
    task = asyncio.create_task(client.patch(ME_URL, headers=headers, json=payload))
    try:
        await asyncio.wait_for(authenticated.wait(), 10)
        confirmed = await client.post(url, json=body)
        assert confirmed.status_code == 204
        confirmed_state = await _snapshot(async_session_maker, user_id)
        assert confirmed_state[0][1] is not None
    finally:
        release.set()
        response = await asyncio.wait_for(task, 10)

    assert response.status_code == 200
    state = await _snapshot(async_session_maker, user_id)
    if change == "email":
        assert state[0][0] == "concurrent-new@example.com"
        assert state[0][1] is None
        assert response.json()["email_verified"] is False
        assert all(used or revoked for _, used, revoked in state[1])
        assert all(used or revoked for _, used, revoked, _, _ in state[2])
    else:
        assert state[0][0:2] == confirmed_state[0][0:2]
        assert state[1:] == confirmed_state[1:]  # No email-change cleanup.
        assert response.json()["email_verified"] is True
        if change == "full_name":
            assert state[0][2] == "Updated Name"
    assert await _snapshot(async_session_maker, foreign_id) == foreign_before
    replay = await client.post(url, json=body)
    assert replay.status_code == 400
    assert replay.json() == {"detail": detail}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
async def test_patch_locks_before_confirmation_rejects_old_credentials(
    client,
    async_session_maker,
    monkeypatch,
    kind,
):
    email = "patch-first@example.com"
    user_id, headers, token, code = await _account(client, email)
    patch_locked = asyncio.Event()
    confirm_started = asyncio.Event()
    release = asyncio.Event()
    patch_session = None
    id_lock = UsersRepository.get_by_id_for_update
    email_lock = UsersRepository.get_by_email_for_update

    async def locked_patch(self, target):
        nonlocal patch_session
        if patch_session is None:
            patch_session = self.db
            user = await id_lock(self, target)
            patch_locked.set()
            await asyncio.wait_for(release.wait(), 10)
            return user
        assert self.db is not patch_session
        confirm_started.set()
        return await id_lock(self, target)

    async def locked_confirmation(self, target):
        assert self.db is not patch_session
        confirm_started.set()
        return await email_lock(self, target)

    monkeypatch.setattr(UsersRepository, "get_by_id_for_update", locked_patch)
    monkeypatch.setattr(UsersRepository, "get_by_email_for_update", locked_confirmation)
    patch = asyncio.create_task(
        client.patch(
            ME_URL,
            headers=headers,
            json={"email": "patch-first-new@example.com"},
        )
    )
    confirmation = None
    try:
        await asyncio.wait_for(patch_locked.wait(), 10)
        url, body, detail = _confirmation(kind, email, token, code)
        confirmation = asyncio.create_task(client.post(url, json=body))
        await asyncio.wait_for(confirm_started.wait(), 10)
    finally:
        release.set()
        response = await asyncio.wait_for(patch, 10)
        if confirmation is not None:
            confirmed = await asyncio.wait_for(confirmation, 10)
    assert response.status_code == 200
    assert confirmed.status_code == 400
    assert confirmed.json() == {"detail": detail}
    state = await _snapshot(async_session_maker, user_id)
    assert state[0][:2] == ("patch-first-new@example.com", None)
    assert all(used is None and revoked for _, used, revoked in state[1])
    assert all(
        used is None and revoked and attempts == 0
        for _, used, revoked, attempts, _ in state[2]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
async def test_cleanup_failure_rolls_back_concurrent_confirmation_email_change(
    client,
    async_session_maker,
    monkeypatch,
    kind,
):
    email = "rollback-concurrent@example.com"
    user_id, headers, token, code = await _account(client, email)
    foreign_id, _, _, _ = await _account(client, "rollback-foreign@example.com")
    foreign_before = await _snapshot(async_session_maker, foreign_id)
    authenticated = asyncio.Event()
    release = asyncio.Event()
    update = UsersService.update_user
    revoke = EmailOtpChallengesRepository.revoke_unused_for_user

    async def pause(self, user_id, data):
        authenticated.set()
        await asyncio.wait_for(release.wait(), 10)
        return await update(self, user_id, data)

    async def fail_after_revocation(self, **kwargs):
        await revoke(self, **kwargs)
        # Both link and OTP cleanup SQL have run inside the PATCH transaction.
        raise RuntimeError("synthetic cleanup failure")

    monkeypatch.setattr(UsersService, "update_user", pause)
    monkeypatch.setattr(
        EmailOtpChallengesRepository, "revoke_unused_for_user", fail_after_revocation
    )
    patch = asyncio.create_task(
        client.patch(
            ME_URL,
            headers=headers,
            json={"email": "rollback-new@example.com"},
        )
    )
    try:
        await asyncio.wait_for(authenticated.wait(), 10)
        url, body, _ = _confirmation(kind, email, token, code)
        confirmed = await client.post(url, json=body)
        assert confirmed.status_code == 204
        before = await _snapshot(async_session_maker, user_id)
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="synthetic cleanup failure"):
            await asyncio.wait_for(patch, 10)
    assert await _snapshot(async_session_maker, user_id) == before
    assert await _snapshot(async_session_maker, foreign_id) == foreign_before
