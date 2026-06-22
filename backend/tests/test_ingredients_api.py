from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
RECIPES_URL = "/api/v1/recipes"
PANTRY_URL = "/api/v1/pantry"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"ingredient-test-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Ingredient Test User",
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


async def create_test_ingredient(
    client: AsyncClient,
    *,
    name: str = "Test Ingredient",
    category: str = "test",
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        json={
            "name": name,
            "category": category,
            "nutrition_value": {
                "calories": "100",
                "protein_g": "10",
                "carbs_g": "5",
                "fat_g": "2",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_ingredient_success(client: AsyncClient) -> None:
    response = await client.post(
        INGREDIENTS_URL,
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
        INGREDIENTS_URL,
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
        INGREDIENTS_URL,
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
        INGREDIENTS_URL,
        json={
            "name": "Tomato",
            "category": "vegetable",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        INGREDIENTS_URL,
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
        INGREDIENTS_URL,
        json={
            "name": "Apple",
            "category": "fruit",
        },
    )
    await client.post(
        INGREDIENTS_URL,
        json={
            "name": "Chicken",
            "category": "meat",
        },
    )

    response = await client.get(INGREDIENTS_URL, params={"search": "app"})

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Apple"


@pytest.mark.asyncio
async def test_get_update_and_delete_ingredient(client: AsyncClient) -> None:
    create_response = await client.post(
        INGREDIENTS_URL,
        json={
            "name": "Potato",
            "category": "vegetable",
        },
    )

    assert create_response.status_code == 201

    ingredient_id = create_response.json()["id"]

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient_id}")

    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Potato"

    update_response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient_id}",
        json={
            "name": "Sweet Potato",
            "category": "root vegetable",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Sweet Potato"
    assert update_response.json()["category"] == "root vegetable"

    delete_response = await client.delete(f"{INGREDIENTS_URL}/{ingredient_id}")

    assert delete_response.status_code == 204

    missing_response = await client.get(f"{INGREDIENTS_URL}/{ingredient_id}")

    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_unused_ingredient_success(client: AsyncClient) -> None:
    ingredient = await create_test_ingredient(
        client,
        name="Unused Ingredient",
    )

    delete_response = await client.delete(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert delete_response.status_code == 204

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_delete_ingredient_used_in_recipe_returns_409(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(
        client,
        name="Recipe Used Ingredient",
    )

    recipe_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Recipe With Ingredient",
            "instructions": "Cook and serve.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert recipe_response.status_code == 201

    delete_response = await client.delete(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert delete_response.status_code == 409
    assert (
        delete_response.json()["detail"] == "Ingredient is used and cannot be deleted"
    )

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_delete_ingredient_used_in_pantry_returns_409(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_test_ingredient(
        client,
        name="Pantry Used Ingredient",
    )

    pantry_response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient["id"],
            "quantity_g": "250",
        },
    )

    assert pantry_response.status_code == 201

    delete_response = await client.delete(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert delete_response.status_code == 409
    assert (
        delete_response.json()["detail"] == "Ingredient is used and cannot be deleted"
    )

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_get_missing_ingredient_returns_404(client: AsyncClient) -> None:
    missing_id = uuid4()

    response = await client.get(f"{INGREDIENTS_URL}/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_delete_missing_ingredient_returns_404(client: AsyncClient) -> None:
    missing_id = uuid4()

    response = await client.delete(f"{INGREDIENTS_URL}/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"
