from uuid import uuid4

import pytest
from httpx import AsyncClient


async def create_test_user(
        client: AsyncClient,
        *,
        email: str = "pavel@example.com",
        full_name: str | None = "Pavel Potapenko",
) -> dict:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": full_name,
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_user_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "  Pavel.User@Example.COM  ",
            "full_name": "  Pavel Potapenko  ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["email"] == "pavel.user@example.com"
    assert data["full_name"] == "Pavel Potapenko"
    assert data["created_at"]
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_get_existing_user(client: AsyncClient) -> None:
    created_user = await create_test_user(client)

    response = await client.get(
        f"/api/v1/users/{created_user['id']}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == created_user["id"]
    assert data["email"] == "pavel@example.com"
    assert data["full_name"] == "Pavel Potapenko"


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_email(
        client: AsyncClient,
) -> None:
    first_response = await client.post(
        "/api/v1/users",
        json={
            "email": "Pavel@Example.COM",
            "full_name": "Pavel",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        "/api/v1/users",
        json={
            "email": "pavel@example.com",
            "full_name": "Another Pavel",
        },
    )

    assert duplicate_response.status_code == 409
    assert (
            duplicate_response.json()["detail"]
            == "User with this email already exists"
    )


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
async def test_create_user_rejects_invalid_email(
        client: AsyncClient,
        invalid_email: str,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": invalid_email,
            "full_name": "Pavel",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_missing_user_returns_404(
        client: AsyncClient,
) -> None:
    missing_user_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{missing_user_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_user_response_does_not_expose_password_hash(
        client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "secure@example.com",
            "full_name": "Secure User",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_blank_full_name_is_normalized_to_null(
        client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "blank-name@example.com",
            "full_name": "   ",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] is None