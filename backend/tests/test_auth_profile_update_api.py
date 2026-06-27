from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
    full_name: str | None = "Profile User",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"profile-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": full_name,
            "password": password,
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    return register_response.json(), {
        "Authorization": f"Bearer {access_token}",
    }


@pytest.mark.asyncio
async def test_update_auth_me_full_name_only(
    client: AsyncClient,
) -> None:
    registered_user, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "full_name": "  Updated Profile User  ",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == registered_user["id"]
    assert data["email"] == registered_user["email"]
    assert data["full_name"] == "Updated Profile User"
    assert data["created_at"]
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_update_auth_me_email_only(
    client: AsyncClient,
) -> None:
    registered_user, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "email": "  Updated.Profile@Example.COM  ",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == registered_user["id"]
    assert data["email"] == "updated.profile@example.com"
    assert data["full_name"] == registered_user["full_name"]


@pytest.mark.asyncio
async def test_update_auth_me_blank_full_name_is_normalized_to_null(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "full_name": "   ",
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
async def test_update_auth_me_full_name_null_clears_name(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "full_name": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["full_name"] is None


@pytest.mark.asyncio
async def test_update_auth_me_allows_current_email(
    client: AsyncClient,
) -> None:
    registered_user, headers = await create_authenticated_user(
        client,
        email=f"current-email-{uuid4()}@example.com",
    )

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "email": f"  {registered_user['email'].upper()}  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


@pytest.mark.asyncio
async def test_update_auth_me_rejects_duplicate_email(
    client: AsyncClient,
) -> None:
    first_user, _ = await create_authenticated_user(
        client,
        email=f"taken-profile-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"available-profile-{uuid4()}@example.com",
    )

    response = await client.patch(
        ME_URL,
        headers=second_headers,
        json={
            "email": f"  {first_user['email'].upper()}  ",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "User with this email already exists"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_email",
    [
        "",
        "   ",
        "not-an-email",
        "pavel@",
        "@example.com",
    ],
)
async def test_update_auth_me_rejects_invalid_email(
    client: AsyncClient,
    invalid_email: str,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "email": invalid_email,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_auth_me_rejects_null_email(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "email": None,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_auth_me_response_does_not_expose_password_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "full_name": "Secure Profile User",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_update_auth_me_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.patch(
        ME_URL,
        json={
            "full_name": "Anonymous Update",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_auth_me_rejects_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.patch(
        ME_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
        json={
            "full_name": "Invalid Token Update",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_auth_me_still_returns_updated_current_user(
    client: AsyncClient,
) -> None:
    registered_user, headers = await create_authenticated_user(client)

    update_response = await client.patch(
        ME_URL,
        headers=headers,
        json={
            "full_name": "Updated Current User",
        },
    )

    assert update_response.status_code == 200

    me_response = await client.get(ME_URL, headers=headers)

    assert me_response.status_code == 200

    data = me_response.json()

    assert data["id"] == registered_user["id"]
    assert data["email"] == registered_user["email"]
    assert data["full_name"] == "Updated Current User"
