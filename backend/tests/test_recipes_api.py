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


@pytest.mark.asyncio
async def test_create_recipe_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await create_test_user(db_session)
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        "/api/v1/recipes",
        json={
            "created_by_user_id": str(user.id),
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
    assert data["created_by_user_id"] == str(user.id)
    assert data["title"] == "High Protein Chicken Bowl"
    assert data["diet_type"] == "high-protein"
    assert Decimal(str(data["total_calories"])) == Decimal("550")
    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_title(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/recipes",
        json={
            "title": "   ",
            "instructions": "Cook everything.",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_recipe_rejects_blank_instructions(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/recipes",
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
    response = await client.post(
        "/api/v1/recipes",
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
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        "/api/v1/recipes",
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
    ingredient_id = await create_test_ingredient(client)

    response = await client.post(
        "/api/v1/recipes",
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
    response = await client.post(
        "/api/v1/recipes",
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
    create_response = await client.post(
        "/api/v1/recipes",
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    title_response = await client.patch(
        f"/api/v1/recipes/{recipe_id}",
        json={
            "title": None,
        },
    )

    assert title_response.status_code == 422

    instructions_response = await client.patch(
        f"/api/v1/recipes/{recipe_id}",
        json={
            "instructions": None,
        },
    )

    assert instructions_response.status_code == 422


@pytest.mark.asyncio
async def test_update_recipe_can_replace_existing_ingredient_quantity(
    client: AsyncClient,
) -> None:
    ingredient_id = await create_test_ingredient(client)

    create_response = await client.post(
        "/api/v1/recipes",
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
        f"/api/v1/recipes/{recipe_id}",
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
async def test_create_recipe_rejects_missing_user(client: AsyncClient) -> None:
    missing_user_id = uuid4()

    response = await client.post(
        "/api/v1/recipes",
        json={
            "created_by_user_id": str(missing_user_id),
            "title": "Missing User Recipe",
            "instructions": "Cook something.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_create_recipe_rejects_missing_ingredient(
    client: AsyncClient,
) -> None:
    missing_ingredient_id = uuid4()

    response = await client.post(
        "/api/v1/recipes",
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
    await client.post(
        "/api/v1/recipes",
        json={
            "title": "Chicken Fitness Bowl",
            "instructions": "Cook chicken.",
            "diet_type": "high-protein",
        },
    )

    await client.post(
        "/api/v1/recipes",
        json={
            "title": "Vegan Salad",
            "instructions": "Cut vegetables.",
            "diet_type": "vegan",
        },
    )

    response = await client.get(
        "/api/v1/recipes",
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
async def test_get_update_and_delete_recipe(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/recipes",
        json={
            "title": "Original Recipe",
            "instructions": "Original instructions.",
            "diet_type": "regular",
        },
    )

    assert create_response.status_code == 201

    recipe_id = create_response.json()["id"]

    get_response = await client.get(f"/api/v1/recipes/{recipe_id}")

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Original Recipe"

    update_response = await client.patch(
        f"/api/v1/recipes/{recipe_id}",
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

    delete_response = await client.delete(f"/api/v1/recipes/{recipe_id}")

    assert delete_response.status_code == 204

    missing_response = await client.get(f"/api/v1/recipes/{recipe_id}")

    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_get_missing_recipe_returns_404(client: AsyncClient) -> None:
    missing_id = uuid4()

    response = await client.get(f"/api/v1/recipes/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"
