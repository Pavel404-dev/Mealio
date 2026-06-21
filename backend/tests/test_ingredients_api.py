from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_ingredient_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Chicken Breast",
            "category": "meat",
            "nutrition_value": {
                "calories": "165",
                "protein_g": "31",
                "carbs_g": "0",
                "fat_g": "3.6",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["name"] == "Chicken Breast"
    assert data["category"] == "meat"
    assert data["nutrition_value"] is not None
    assert Decimal(str(data["nutrition_value"]["calories"])) == Decimal("165")


@pytest.mark.asyncio
async def test_create_ingredient_rejects_blank_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "   ",
            "category": "vegetable",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_ingredient_normalizes_blank_category_to_null(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Rice",
            "category": "   ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Rice"
    assert data["category"] is None


@pytest.mark.asyncio
async def test_create_ingredient_rejects_duplicate_name(client: AsyncClient) -> None:
    first_response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Tomato",
            "category": "vegetable",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "tomato",
            "category": "vegetable",
        },
    )

    assert duplicate_response.status_code == 409
    assert (
        duplicate_response.json()["detail"]
        == "Ingredient with this name already exists"
    )


@pytest.mark.asyncio
async def test_list_ingredients_with_search(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Apple",
            "category": "fruit",
        },
    )
    await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Chicken",
            "category": "meat",
        },
    )

    response = await client.get("/api/v1/ingredients", params={"search": "app"})

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Apple"


@pytest.mark.asyncio
async def test_get_update_and_delete_ingredient(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": "Potato",
            "category": "vegetable",
        },
    )

    assert create_response.status_code == 201

    ingredient_id = create_response.json()["id"]

    get_response = await client.get(f"/api/v1/ingredients/{ingredient_id}")

    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Potato"

    update_response = await client.patch(
        f"/api/v1/ingredients/{ingredient_id}",
        json={
            "name": "Sweet Potato",
            "category": "root vegetable",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Sweet Potato"
    assert update_response.json()["category"] == "root vegetable"

    delete_response = await client.delete(f"/api/v1/ingredients/{ingredient_id}")

    assert delete_response.status_code == 204

    missing_response = await client.get(f"/api/v1/ingredients/{ingredient_id}")

    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_get_missing_ingredient_returns_404(client: AsyncClient) -> None:
    missing_id = uuid4()

    response = await client.get(f"/api/v1/ingredients/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"
