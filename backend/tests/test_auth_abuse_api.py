import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.api.deps import get_password_reset_mailer
from app.main import app


LOGIN_URL = "/api/v1/auth/login"
REGISTER_URL = "/api/v1/auth/register"
PASSWORD_RESET_REQUEST_URL = "/api/v1/auth/password-reset/request"
LIMIT_DETAIL = "Too many authentication requests. Please try again later."
GENERIC_RESET_MESSAGE = (
    "If an account with that email exists, password reset instructions have been sent."
)


class FakePasswordResetMailer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def send_password_reset(
        self,
        *,
        recipient_email: str,
        reset_token: SecretStr,
    ) -> None:
        self.calls.append(recipient_email)


def _assert_rate_limited(response) -> None:
    assert response.status_code == 429
    assert response.json() == {"detail": LIMIT_DETAIL}
    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None
    assert retry_after.isascii()
    assert retry_after.isdigit()
    assert int(retry_after) >= 1


@pytest.mark.asyncio
async def test_login_email_limit_uses_normalized_email(
    client: AsyncClient,
) -> None:
    for index in range(10):
        email = "  UNKNOWN@EXAMPLE.COM  " if index % 2 == 0 else "unknown@example.com"
        response = await client.post(
            LOGIN_URL,
            json={
                "email": email,
                "password": "Mealio-password-123",
            },
        )
        assert response.status_code == 401

    blocked = await client.post(
        LOGIN_URL,
        json={
            "email": "unknown@example.com",
            "password": "Mealio-password-123",
        },
    )

    _assert_rate_limited(blocked)


@pytest.mark.asyncio
async def test_spoofed_forwarded_ip_cannot_bypass_ip_limit(
    client: AsyncClient,
) -> None:
    for index in range(30):
        response = await client.post(
            LOGIN_URL,
            headers={"X-Forwarded-For": f"198.51.100.{index + 1}"},
            json={
                "email": f"unknown-{index}@example.com",
                "password": "Mealio-password-123",
            },
        )
        assert response.status_code == 401

    blocked = await client.post(
        LOGIN_URL,
        headers={"X-Forwarded-For": "203.0.113.250"},
        json={
            "email": "unknown-final@example.com",
            "password": "Mealio-password-123",
        },
    )

    _assert_rate_limited(blocked)


@pytest.mark.asyncio
async def test_password_reset_rate_limit_preserves_generic_account_behavior(
    client: AsyncClient,
) -> None:
    mailer = FakePasswordResetMailer()
    app.dependency_overrides[get_password_reset_mailer] = lambda: mailer

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": "reset-existing@example.com",
            "full_name": "Reset Existing",
            "password": "Mealio-password-123",
        },
    )
    assert register_response.status_code == 201

    for email in (
        "reset-existing@example.com",
        "does-not-exist@example.com",
    ):
        for _ in range(3):
            response = await client.post(
                PASSWORD_RESET_REQUEST_URL,
                json={"email": email},
            )
            assert response.status_code == 202
            assert response.json() == {"message": GENERIC_RESET_MESSAGE}

        blocked = await client.post(
            PASSWORD_RESET_REQUEST_URL,
            json={"email": email},
        )
        _assert_rate_limited(blocked)

    assert mailer.calls == ["reset-existing@example.com"] * 3


@pytest.mark.asyncio
async def test_direct_peer_address_is_used_by_asgi_transport(
    client: AsyncClient,
) -> None:
    transport = ASGITransport(
        app=app,
        client=("203.0.113.25", 4242),
    )
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as alternate_client:
        for index in range(30):
            response = await alternate_client.post(
                LOGIN_URL,
                json={
                    "email": f"alternate-{index}@example.com",
                    "password": "Mealio-password-123",
                },
            )
            assert response.status_code == 401

        blocked = await alternate_client.post(
            LOGIN_URL,
            json={
                "email": "alternate-final@example.com",
                "password": "Mealio-password-123",
            },
        )

    _assert_rate_limited(blocked)
