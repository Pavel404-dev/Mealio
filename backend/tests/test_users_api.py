from uuid import uuid4

import pytest
from httpx import AsyncClient


USERS_URL = "/api/v1/users"


@pytest.mark.asyncio
async def test_legacy_create_user_endpoint_is_not_exposed(
    client: AsyncClient,
) -> None:
    response = await client.post(
        USERS_URL,
        json={
            "email": "legacy-create@example.com",
            "full_name": "Legacy Create User",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_get_user_by_id_endpoint_is_not_exposed(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{USERS_URL}/{uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_update_user_by_id_endpoint_is_not_exposed(
    client: AsyncClient,
) -> None:
    response = await client.patch(
        f"{USERS_URL}/{uuid4()}",
        json={
            "full_name": "Legacy Updated User",
        },
    )

    assert response.status_code == 404
