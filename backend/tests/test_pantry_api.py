from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def create_test_user(db_session: AsyncSession) -> User:
    user = User(
        email="test-user@example.com",
        password_hash="test-password-hash",
        full_name="Test User",
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


async def create_test_ingredient(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Oats",
            "category": "grain",
            "nutrition_value": {
                "calories": "389",
                "protein_g": "16.9",
                "carbs_g": "66.3",
                "fat_g": "6.9",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_add_list_update_and_delete_pantry_item(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    ingredient = await create_test_ingredient(client)

    add_response = await client.post(
        f"/api/v1/users/{user.id}/pantry",
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "250",
        },
    )

    assert add_response.status_code == 201

    pantry_item = add_response.json()

    assert pantry_item["id"]
    assert pantry_item["user_id"] == str(user.id)
    assert pantry_item["ingredient_id"] == ingredient["id"]
    assert Decimal(str(pantry_item["quantity_g"])) == Decimal("250")
    assert pantry_item["ingredient"]["name"] == "Oats"

    list_response = await client.get(f"/api/v1/users/{user.id}/pantry")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = await client.patch(
        f"/api/v1/users/{user.id}/pantry/{pantry_item['id']}",
        json={
            "quantity_g": "500",
        },
    )

    assert update_response.status_code == 200
    assert Decimal(str(update_response.json()["quantity_g"])) == Decimal("500")

    delete_response = await client.delete(
        f"/api/v1/users/{user.id}/pantry/{pantry_item['id']}"
    )

    assert delete_response.status_code == 204

    empty_list_response = await client.get(f"/api/v1/users/{user.id}/pantry")

    assert empty_list_response.status_code == 200
    assert empty_list_response.json() == []


@pytest.mark.asyncio
async def test_add_duplicate_pantry_item_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    ingredient = await create_test_ingredient(client)

    first_response = await client.post(
        f"/api/v1/users/{user.id}/pantry",
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "100",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        f"/api/v1/users/{user.id}/pantry",
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "200",
        },
    )

    assert duplicate_response.status_code == 409
    assert (
        duplicate_response.json()["detail"]
        == "Ingredient already exists in user pantry"
    )


@pytest.mark.asyncio
async def test_pantry_returns_404_when_user_does_not_exist(
    client: AsyncClient,
) -> None:
    missing_user_id = uuid4()

    response = await client.get(f"/api/v1/users/{missing_user_id}/pantry")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_add_pantry_item_returns_404_when_ingredient_does_not_exist(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    missing_ingredient_id = uuid4()

    response = await client.post(
        f"/api/v1/users/{user.id}/pantry",
        json={
            "ingredient_id": str(missing_ingredient_id),
            "quantity_g": "100",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_add_pantry_item_rejects_invalid_quantity(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    ingredient = await create_test_ingredient(client)

    response = await client.post(
        f"/api/v1/users/{user.id}/pantry",
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "0",
        },
    )

    assert response.status_code == 422
