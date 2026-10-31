"""Request validation and stored response compatibility through real HTTP paths."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.models.ingredient import NutritionValue, UserIngredient
from app.models.recipe import Recipe
from tests.test_ai_recipe_save_api import (
    AI_RECIPE_SAVE_URL,
    INGREDIENTS_URL,
    PANTRY_URL,
    RECIPES_URL,
    create_authenticated_user,
    create_ingredient,
    save_payload,
)


async def test_invalid_writes_do_not_mutate_and_exact_forms_reload(
    client, async_session_maker
):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(
        client, headers=headers, name="W9 API original", calories="100", portion_g="50"
    )
    for value in ["1.234", "1000000", True, "NaN", "1e-99"]:
        response = await client.patch(
            f"{INGREDIENTS_URL}/{ingredient}",
            headers=headers,
            json={
                "name": "should not persist",
                "category": "changed",
                "nutrition_value": {"calories": value},
            },
        )
        assert response.status_code == 422
    original = (await client.get(f"{INGREDIENTS_URL}/{ingredient}")).json()
    assert original["name"] == "W9 API original"
    for value in ["0.004", "1.234", "100000000", True, "Infinity"]:
        for endpoint in [RECIPES_URL, AI_RECIPE_SAVE_URL, PANTRY_URL]:
            if endpoint == PANTRY_URL:
                payload = dict(ingredient_id=ingredient, quantity_g=value)
            else:
                payload = save_payload(
                    ingredient,
                    ingredients=[dict(ingredient_id=ingredient, quantity_g=value)],
                )
                if endpoint == RECIPES_URL:
                    payload["instructions"] = "Mix"
            response = await client.post(endpoint, headers=headers, json=payload)
            assert response.status_code == 422, (endpoint, value, response.text)
    async with async_session_maker() as db:
        assert await db.scalar(select(func.count()).select_from(Recipe)) == 0
        assert await db.scalar(select(func.count()).select_from(UserIngredient)) == 0
    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json=dict(ingredient_id=ingredient, quantity_g="1.2300"),
    )
    assert response.status_code == 201
    pantry_id = response.json()["id"]
    response = await client.patch(
        f"{PANTRY_URL}/{pantry_id}", headers=headers, json=dict(quantity_g="0.004")
    )
    assert response.status_code == 422
    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient,
            ingredients=[dict(ingredient_id=ingredient, quantity_g="125.000")],
        ),
    )
    assert response.status_code == 201
    assert response.json()["total_calories"] == "250.00"
    async with async_session_maker() as db:
        assert await db.scalar(select(UserIngredient.quantity_g)) == Decimal("1.23")
        nutrition = await db.scalar(
            select(NutritionValue).where(
                NutritionValue.ingredient_id == UUID(ingredient)
            )
        )
        assert nutrition.portion_g == 50
        assert nutrition.calories == 100
        assert await db.scalar(select(Recipe.total_calories)) == Decimal("250.00")
    response = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient}",
        headers=headers,
        json={
            "name": "overflow name",
            "category": "overflow",
            "nutrition_value": {"calories": "999999.99", "portion_g": "0.01"},
        },
    )
    assert response.status_code == 422
    assert (await client.get(f"{INGREDIENTS_URL}/{ingredient}")).json() == original
    async with async_session_maker() as db:
        assert await db.scalar(select(Recipe.total_calories)) == Decimal("250.00")


@pytest.mark.parametrize("level", ["root", "ingredient"])
@pytest.mark.parametrize(
    "field",
    [
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "total_calories",
        "total_protein_g",
        "total_carbs_g",
        "total_fat_g",
    ],
)
async def test_ai_save_http_rejects_injected_nutrients(
    client, async_session_maker, level, field
):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient)
    target = payload if level == "root" else payload["ingredients"][0]
    target[field] = "999"
    response = await client.post(AI_RECIPE_SAVE_URL, headers=headers, json=payload)
    assert response.status_code == 422
    async with async_session_maker() as db:
        assert await db.scalar(select(func.count()).select_from(Recipe)) == 0
