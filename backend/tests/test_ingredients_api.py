from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
RECIPES_URL = "/api/v1/recipes"
PANTRY_URL = "/api/v1/pantry"

INVALID_TOKEN_HEADERS = {
    "Authorization": "Bearer invalid-token",
}


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


def default_nutrition_value() -> dict[str, str]:
    return {
        "calories": "100",
        "protein_g": "10",
        "carbs_g": "5",
        "fat_g": "2",
        "portion_g": "100",
    }


def ingredient_payload(
    *,
    name: str,
    category: str | None = "test",
    nutrition_value: dict[str, str] | None = None,
) -> dict:
    return {
        "name": name,
        "category": category,
        "nutrition_value": nutrition_value or default_nutrition_value(),
    }


async def create_test_ingredient(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str = "Test Ingredient",
    category: str | None = "test",
    nutrition_value: dict[str, str] | None = None,
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json=ingredient_payload(
            name=name,
            category=category,
            nutrition_value=nutrition_value,
        ),
    )

    assert response.status_code == 201

    return response.json()


def assert_decimal(value, expected: str) -> None:
    assert Decimal(str(value)) == Decimal(expected)


@pytest.mark.asyncio
async def test_unauthenticated_create_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        INGREDIENTS_URL,
        json=ingredient_payload(
            name="Chicken Breast",
            category="meat",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_update_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    ingredient_id = uuid4()

    response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient_id}",
        json={
            "name": "Updated Ingredient",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_delete_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    ingredient_id = uuid4()

    response = await client.delete(f"{INGREDIENTS_URL}/{ingredient_id}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_create_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        INGREDIENTS_URL,
        headers=INVALID_TOKEN_HEADERS,
        json=ingredient_payload(
            name="Invalid Token Chicken",
            category="meat",
        ),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_invalid_token_update_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    ingredient_id = uuid4()

    response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient_id}",
        headers=INVALID_TOKEN_HEADERS,
        json={
            "name": "Invalid Token Update",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_invalid_token_delete_ingredient_returns_401(
    client: AsyncClient,
) -> None:
    ingredient_id = uuid4()

    response = await client.delete(
        f"{INGREDIENTS_URL}/{ingredient_id}",
        headers=INVALID_TOKEN_HEADERS,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_authenticated_create_ingredient_still_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json=ingredient_payload(
            name="Chicken Breast",
            category="meat",
            nutrition_value={
                "calories": "165",
                "protein_g": "31",
                "carbs_g": "0",
                "fat_g": "3.6",
                "portion_g": "100",
            },
        ),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["name"] == "Chicken Breast"
    assert data["category"] == "meat"
    assert data["nutrition_value"] is not None
    assert Decimal(str(data["nutrition_value"]["calories"])) == Decimal("165")


@pytest.mark.asyncio
async def test_authenticated_update_ingredient_still_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name="Potato",
        category="vegetable",
    )

    response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
        json={
            "name": "Sweet Potato",
            "category": "root vegetable",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Sweet Potato"
    assert response.json()["category"] == "root vegetable"


@pytest.mark.asyncio
async def test_authenticated_delete_unused_ingredient_still_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name="Unused Ingredient",
    )

    delete_response = await client.delete(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 204

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_public_list_ingredients_still_works_without_token(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_ingredient(
        client,
        headers=headers,
        name="Apple",
        category="fruit",
    )
    await create_test_ingredient(
        client,
        headers=headers,
        name="Chicken",
        category="meat",
    )

    response = await client.get(INGREDIENTS_URL, params={"search": "app"})

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Apple"


@pytest.mark.asyncio
async def test_public_get_ingredient_by_id_still_works_without_token(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name="Public Potato",
        category="vegetable",
    )

    response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Public Potato"
    assert response.json()["category"] == "vegetable"


@pytest.mark.asyncio
async def test_create_ingredient_rejects_blank_name(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
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
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
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
async def test_create_ingredient_rejects_duplicate_name(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    first_response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": "Tomato",
            "category": "vegetable",
        },
    )

    assert first_response.status_code == 201

    duplicate_response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
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
async def test_delete_ingredient_used_in_recipe_returns_409(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        headers=headers,
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

    delete_response = await client.delete(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
    )

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
        headers=headers,
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

    delete_response = await client.delete(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 409
    assert (
        delete_response.json()["detail"] == "Ingredient is used and cannot be deleted"
    )

    get_response = await client.get(f"{INGREDIENTS_URL}/{ingredient['id']}")

    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_updating_ingredient_nutrition_recalculates_recipe_totals(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=f"Recalc Chicken {uuid4()}",
        nutrition_value={
            "calories": "100",
            "protein_g": "10",
            "carbs_g": "5",
            "fat_g": "2",
            "portion_g": "100",
        },
    )

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Recipe Using Updated Ingredient",
            "instructions": "Cook.",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    assert_decimal(create_response.json()["total_calories"], "200")
    assert_decimal(create_response.json()["total_protein_g"], "20")
    assert_decimal(create_response.json()["total_carbs_g"], "10")
    assert_decimal(create_response.json()["total_fat_g"], "4")

    update_ingredient_response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient['id']}",
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "150",
                "protein_g": "20",
                "carbs_g": "10",
                "fat_g": "4",
                "portion_g": "100",
            }
        },
    )

    assert update_ingredient_response.status_code == 200

    recipe_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert recipe_response.status_code == 200

    data = recipe_response.json()

    assert_decimal(data["total_calories"], "300")
    assert_decimal(data["total_protein_g"], "40")
    assert_decimal(data["total_carbs_g"], "20")
    assert_decimal(data["total_fat_g"], "8")


@pytest.mark.asyncio
async def test_get_missing_ingredient_returns_404(client: AsyncClient) -> None:
    missing_id = uuid4()

    response = await client.get(f"{INGREDIENTS_URL}/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"


@pytest.mark.asyncio
async def test_authenticated_delete_missing_ingredient_returns_404(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    missing_id = uuid4()

    response = await client.delete(
        f"{INGREDIENTS_URL}/{missing_id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"
