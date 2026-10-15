"""Both owner-lock orders for HTTP recovery confirmation/issuance versus PATCH."""

import asyncio

import pytest

from app.core.security import verify_password
from app.repositories.users import UsersRepository
from tests.test_auth_email_change_password_reset_api import (
    NEW_EMAIL,
    OLD_EMAIL,
    _account,
    _change,
    _confirm,
    _confirmation,
    _snapshot,
)
from tests.test_auth_email_change_password_reset_api import (
    recovery_mailers as _recovery_mailers,
)
from tests.test_auth_password_reset_confirm_api import (
    INVALID_RESET_DETAIL,
    NEW_PASSWORD,
    OLD_PASSWORD,
)
from tests.test_auth_password_reset_otp_confirm_api import (
    INVALID_DETAIL,
    LINK_REQUEST_URL,
    ME_URL,
    OTP_REQUEST_URL,
)


recovery_mailers = _recovery_mailers


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["link", "otp"])
@pytest.mark.parametrize("operation", ["confirm", "issue"])
@pytest.mark.parametrize("first", ["patch", "recovery"])
async def test_recovery_and_email_change_follow_owner_lock_order(
    client, async_session_maker, recovery_mailers, monkeypatch, kind, operation, first
):
    user_id, headers, _, token, code = await _account(
        client, recovery_mailers, issue=operation == "confirm"
    )
    foreign_id, _, _, _, _ = await _account(
        client, recovery_mailers, "foreign@example.com"
    )
    foreign = await _snapshot(async_session_maker, foreign_id)
    before = await _snapshot(async_session_maker, user_id)
    first_locked = asyncio.Event()
    second_attempted = asyncio.Event()
    release = asyncio.Event()
    sessions = {}

    def instrument(lock):
        async def gated(self, target):
            role = asyncio.current_task().get_name()
            assert role in {"patch", "recovery"}
            sessions[role] = self.db
            if role == first:
                user = await lock(self, target)
                assert user is not None and user.id == user_id
                first_locked.set()
                await asyncio.wait_for(release.wait(), timeout=10)
                return user
            assert first_locked.is_set()
            assert self.db is not sessions[first]
            second_attempted.set()
            return await lock(self, target)

        return gated

    # Instrument existing repository boundaries, retaining real PostgreSQL locks.
    with monkeypatch.context() as patch:
        for name in ("get_by_id_for_update", "get_by_email_for_update"):
            patch.setattr(
                UsersRepository, name, instrument(getattr(UsersRepository, name))
            )

        if operation == "confirm":
            url, body = _confirmation(kind, OLD_EMAIL, token, code)
        else:
            url = LINK_REQUEST_URL if kind == "link" else OTP_REQUEST_URL
            body = {"email": OLD_EMAIL}
        mailer = recovery_mailers[0 if kind == "link" else 1]
        delivered_before = len(mailer.calls)

        def start(role):
            request = (
                client.patch(ME_URL, headers=headers, json={"email": NEW_EMAIL})
                if role == "patch"
                else client.post(url, json=body)
            )
            return asyncio.create_task(request, name=role)

        tasks = {}
        try:
            tasks[first] = start(first)
            await asyncio.wait_for(first_locked.wait(), timeout=10)
            second = "recovery" if first == "patch" else "patch"
            tasks[second] = start(second)
            await asyncio.wait_for(second_attempted.wait(), timeout=10)
            assert not tasks[second].done()
            release.set()
            responses = await asyncio.wait_for(
                asyncio.gather(tasks["patch"], tasks["recovery"]), timeout=10
            )
        finally:
            release.set()
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True), 10
            )

    changed, recovered = responses
    assert changed.status_code == 200
    assert changed.json()["email"] == NEW_EMAIL
    assert changed.json()["email_verified"] is False
    if operation == "confirm":
        assert recovered.status_code == (204 if first == "recovery" else 400)
        if first == "patch":
            assert recovered.json() == {
                "detail": INVALID_RESET_DETAIL if kind == "link" else INVALID_DETAIL
            }
    else:
        assert recovered.status_code == 202
        assert len(mailer.calls) == delivered_before + (first == "recovery")
        if first == "recovery":
            assert mailer.calls[-1][0] == OLD_EMAIL
            if kind == "link":
                token = mailer.calls[-1][1]
            else:
                code = mailer.calls[-1][1]

    after = await _snapshot(async_session_maker, user_id)
    reset_committed = operation == "confirm" and first == "recovery"
    assert verify_password(
        NEW_PASSWORD if reset_committed else OLD_PASSWORD,
        after["users"][0]["password_hash"],
    )
    if reset_committed:
        assert all(row["revoked_at"] for row in after["auth_sessions"])
        table = "password_reset_tokens" if kind == "link" else "email_otp_challenges"
        assert any(row["used_at"] for row in after[table])
    else:
        assert after["auth_sessions"] == before["auth_sessions"]
        assert after["users"][0]["password_hash"] == before["users"][0]["password_hash"]
    for table in (
        "password_reset_tokens",
        "email_otp_challenges",
        "email_verification_tokens",
    ):
        assert all(row["used_at"] or row["revoked_at"] for row in after[table])
    assert await _snapshot(async_session_maker, foreign_id) == foreign
    if operation == "confirm" or first == "recovery":
        # Returning to the issuing address must not resurrect the original OTP.
        await _change(client, headers, OLD_EMAIL)
        before_replay = await _snapshot(async_session_maker, user_id)
        await _confirm(client, kind, OLD_EMAIL, token, code, expected=400)
        assert await _snapshot(async_session_maker, user_id) == before_replay
