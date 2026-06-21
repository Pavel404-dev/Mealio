from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
RECIPES_URL = "/api/v1/recipes"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"test-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Test User",
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
    name: str = "Chicken Breast",
) -> str:
    response = await client.post(
        "/api/v1/ingredients",
        json={
            "name": name,
            "category": "protein",
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

    return response.json()["id"]


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str = "Test Recipe",
    instructions: str = "Cook and serve.",
    diet_type: str | None = None,
) -> dict:
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": title,
            "instructions": instructions,
            "diet_type": diet_type,
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_create_recipe_success(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "High Protein Chicken Bowl",
            "description": "Simple protein meal",
            "instructions": "Cook chicken and serve with rice.",
            "diet_type": "high-protein",
            "total_calories": "550",
            "total_protein_g": "45",
            "total_carbs_g": "55",
            "total_fat_g": "12",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "200",
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"]
    assert data["created_by_user_id"] == user["id"]
    assert data["title"] == "High Protein Chicken Bowl"
    assert data["diet_type"] == "high-protein"
    assert Decimal(str(data["total_calories"])) == Decimal("550")
    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id


@pytest.mark.asyncio
async def test_create_recipe_rejects_client_created_by_user_id(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "created_by_user_id": str(uuid4()),
            "title": "Client Owned Recipe",
            "instructions": "Cook something.",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_title(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "   ",
            "instructions": "Cook everything.",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_instructions(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Simple Recipe",
            "instructions": "   ",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_normalizes_blank_optional_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Simple Rice",
            "description": "   ",
            "instructions": "Boil rice.",
            "diet_type": "   ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["description"] is None
    assert data["diet_type"] is None


@pytest.mark.asyncio
async def test_create_recipe_rejects_duplicate_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Duplicate Ingredient Recipe",
            "instructions": "Cook ingredients.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "100",
                },
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "200",
                },
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_non_positive_ingredient_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Invalid Quantity Recipe",
            "instructions": "Cook ingredients.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "0",
                }
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_negative_nutrition_total(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Invalid Nutrition Recipe",
            "instructions": "Cook something.",
            "total_calories": "-100",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_recipe_rejects_null_required_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    title_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "title": None,
        },
    )

    assert title_response.status_code == 422

    instructions_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "instructions": None,
        },
    )

    assert instructions_response.status_code == 422


@pytest.mark.asyncio
async def test_update_recipe_can_replace_existing_ingredient_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_test_ingredient(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Bowl",
            "instructions": "Cook chicken.",
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    update_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "ingredients": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "250",
                }
            ],
        },
    )

    assert update_response.status_code == 200

    data = update_response.json()

    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id
    assert Decimal(str(data["recipe_ingredients"][0]["quantity_g"])) == Decimal("250")


@pytest.mark.asyncio
async def test_create_recipe_rejects_missing_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    missing_ingredient_id = uuid4()

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Missing Ingredient Recipe",
            "instructions": "Cook something.",
            "ingredients": [
                {
                    "ingredient_id": str(missing_ingredient_id),
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert response.status_code == 404
    assert "Ingredients not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_recipes_with_search_and_diet_type(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Chicken Fitness Bowl",
            "instructions": "Cook chicken.",
            "diet_type": "high-protein",
        },
    )

    await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Vegan Salad",
            "instructions": "Cut vegetables.",
            "diet_type": "vegan",
        },
    )

    response = await client.get(
        RECIPES_URL,
        headers=headers,
        params={
            "search": "chicken",
            "diet_type": "high-protein",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Chicken Fitness Bowl"


@pytest.mark.asyncio
async def test_list_recipes_returns_only_current_users_recipes(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-list-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-list-user-{uuid4()}@example.com",
    )

    first_recipe_response = await client.post(
        RECIPES_URL,
        headers=first_headers,
        json={
            "title": "First User Chicken Bowl",
            "instructions": "Cook chicken.",
            "diet_type": "high-protein",
        },
    )

    assert first_recipe_response.status_code == 201

    second_recipe_response = await client.post(
        RECIPES_URL,
        headers=second_headers,
        json={
            "title": "Second User Vegan Salad",
            "instructions": "Cut vegetables.",
            "diet_type": "vegan",
        },
    )

    assert second_recipe_response.status_code == 201

    first_user_list_response = await client.get(
        RECIPES_URL,
        headers=first_headers,
    )

    assert first_user_list_response.status_code == 200

    first_user_recipes = first_user_list_response.json()

    assert len(first_user_recipes) == 1
    assert first_user_recipes[0]["title"] == "First User Chicken Bowl"

    second_user_list_response = await client.get(
        RECIPES_URL,
        headers=second_headers,
    )

    assert second_user_list_response.status_code == 200

    second_user_recipes = second_user_list_response.json()

    assert len(second_user_recipes) == 1
    assert second_user_recipes[0]["title"] == "Second User Vegan Salad"


@pytest.mark.asyncio
async def test_get_update_and_delete_recipe(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    create_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
            "diet_type": "regular",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    get_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Original Recipe"

    update_response = await client.patch(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
        json={
            "title": "Updated Recipe",
            "instructions": "Updated instructions.",
            "diet_type": "high-protein",
            "total_calories": "700",
        },
    )

    assert update_response.status_code == 200

    updated_data = update_response.json()

    assert updated_data["title"] == "Updated Recipe"
    assert updated_data["instructions"] == "Updated instructions."
    assert updated_data["diet_type"] == "high-protein"
    assert Decimal(str(updated_data["total_calories"])) == Decimal("700")

    delete_response = await client.delete(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"{RECIPES_URL}/{recipe_id}",
        headers=headers,
    )

    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_get_missing_recipe_returns_404(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    missing_id = uuid4()

    response = await client.get(
        f"{RECIPES_URL}/{missing_id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    (
        ("GET", RECIPES_URL, {}),
        (
            "POST",
            RECIPES_URL,
            {
                "json": {
                    "title": "Auth Recipe",
                    "instructions": "Cook something.",
                }
            },
        ),
        ("GET", f"{RECIPES_URL}/{uuid4()}", {}),
        (
            "PATCH",
            f"{RECIPES_URL}/{uuid4()}",
            {
                "json": {
                    "title": "Updated Recipe",
                }
            },
        ),
        ("DELETE", f"{RECIPES_URL}/{uuid4()}", {}),
    ),
)
@pytest.mark.asyncio
async def test_recipe_endpoints_require_authentication(
    client: AsyncClient,
    method: str,
    url: str,
    kwargs: dict,
) -> None:
    response = await client.request(method, url, **kwargs)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    (
        ("GET", RECIPES_URL, {}),
        (
            "POST",
            RECIPES_URL,
            {
                "json": {
                    "title": "Auth Recipe",
                    "instructions": "Cook something.",
                }
            },
        ),
        ("GET", f"{RECIPES_URL}/{uuid4()}", {}),
        (
            "PATCH",
            f"{RECIPES_URL}/{uuid4()}",
            {
                "json": {
                    "title": "Updated Recipe",
                }
            },
        ),
        ("DELETE", f"{RECIPES_URL}/{uuid4()}", {}),
    ),
)
@pytest.mark.asyncio
async def test_recipe_endpoints_reject_invalid_token(
    client: AsyncClient,
    method: str,
    url: str,
    kwargs: dict,
) -> None:
    response = await client.request(
        method,
        url,
        headers={
            "Authorization": "Bearer invalid-token",
        },
        **kwargs,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_user_cannot_update_or_delete_another_users_recipe(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email=f"first-recipe-user-{uuid4()}@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email=f"second-recipe-user-{uuid4()}@example.com",
    )

    create_response = await client.post(
        RECIPES_URL,
        headers=first_headers,
        json={
            "title": "Private Recipe",
            "instructions": "Cook privately.",
        },
    )

    assert create_response.status_code == 201

    recipe = create_response.json()

    assert recipe["created_by_user_id"] == first_user["id"]
    assert recipe["created_by_user_id"] != second_user["id"]

    second_user_get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
    )

    assert second_user_get_response.status_code == 404
    assert second_user_get_response.json()["detail"] == "Recipe not found"

    second_user_update_response = await client.patch(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
        json={
            "title": "Hacked Recipe",
        },
    )

    assert second_user_update_response.status_code == 404
    assert second_user_update_response.json()["detail"] == "Recipe not found"

    second_user_delete_response = await client.delete(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
    )

    assert second_user_delete_response.status_code == 404
    assert second_user_delete_response.json()["detail"] == "Recipe not found"

    first_user_get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=first_headers,
    )

    assert first_user_get_response.status_code == 200
    assert first_user_get_response.json()["title"] == "Private Recipe"
