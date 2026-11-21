"""PostgreSQL witness for owner-scoped candidates, eligibility and read-only preview."""

import json
from uuid import UUID

import pytest

from app.api.deps import get_meal_plan_generation_provider
from app.integrations.meal_plan_generation import MealPlanProviderResult
from app.main import app
from app.models.ingredient import IngredientAllergenVerification
from app.models.user_nutrition_profile import UserNutritionProfile
from tests.test_ai_meal_plan_preview import REQUEST, URL, selection
from tests.test_meal_plan_portions_api import ingredient, recipe
from tests.test_meal_plans_api import create_authenticated_user


async def test_live_repository_excludes_foreign_and_incomplete_recipes(
    client, monkeypatch
):
    _, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    component = await ingredient(client, owner)
    own_recipe = await recipe(client, owner, component["id"])
    await recipe(client, other, component["id"])
    unknown = await client.post(
        "/api/v1/ingredients", headers=owner, json={"name": "No nutrition for preview"}
    )
    assert unknown.status_code == 201
    mixed = await client.post(
        "/api/v1/recipes",
        headers=owner,
        json={
            "title": "Incomplete nutrition",
            "instructions": "Mix.",
            "servings": 4,
            "ingredients": [
                {"ingredient_id": component["id"], "quantity_g": "200"},
                {"ingredient_id": unknown.json()["id"], "quantity_g": "20"},
            ],
        },
    )
    assert mixed.status_code == 201 and mixed.json()["total_calories"] is not None

    class Provider:
        model = "test-plan-model"
        candidate = 1

        async def select_meals(self, *, context_json):
            context = json.loads(context_json)
            assert len(context["candidates"]) == 1
            return MealPlanProviderResult(
                {"items": [selection(candidate=self.candidate)]}
            )

    provider = Provider()
    monkeypatch.setitem(
        app.dependency_overrides, get_meal_plan_generation_provider, lambda: provider
    )
    payload = {**REQUEST, "meal_types": ["lunch"]}
    response = await client.post(URL, headers=owner, json=payload)
    assert response.status_code == 200
    assert response.json()["items"][0]["recipe_id"] == own_recipe["id"]
    assert response.json()["nutrition"]["total_calories"] == "82.50"
    provider.candidate = 2
    rejected = await client.post(URL, headers=owner, json=payload)
    assert rejected.status_code == 502
    plans = await client.get("/api/v2/meal-plans", headers=owner)
    assert plans.status_code == 200 and plans.json() == []


@pytest.mark.parametrize("sesame_status", [None, "present", "possible"])
async def test_allergen_coverage_requires_absence_on_every_ingredient(
    client, db_session, monkeypatch, sesame_status
):
    account, headers = await create_authenticated_user(client)
    reviewed = await ingredient(client, headers)
    other = await ingredient(client, headers)
    eligible = await recipe(client, headers, reviewed["id"])
    mixed = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "title": "Partially reviewed recipe",
            "instructions": "Mix.",
            "ingredients": [
                {"ingredient_id": reviewed["id"], "quantity_g": 200},
                {"ingredient_id": other["id"], "quantity_g": 20},
            ],
        },
    )
    assert mixed.status_code == 201, mixed.text

    db_session.add(
        UserNutritionProfile(user_id=UUID(account["id"]), allergies=[" SOY ", "Sesame"])
    )
    statuses = [
        (reviewed["id"], "soy", "absent"),
        (reviewed["id"], "sesame", "absent"),
        (other["id"], "soy", "absent"),
    ]
    if sesame_status is not None:
        statuses.append((other["id"], "sesame", sesame_status))
    db_session.add_all(
        [
            IngredientAllergenVerification(
                ingredient_id=UUID(ingredient_id),
                allergen_key=key,
                status=status,
                source_name="Synthetic review evidence",
                source_reference="Synthetic record 1",
            )
            for ingredient_id, key, status in statuses
        ]
    )
    await db_session.commit()

    class Provider:
        model = "allergen-test-model"

        async def select_meals(self, *, context_json):
            context = json.loads(context_json)
            assert len(context["candidates"]) == 1
            assert context["preferences"]["allergies"] == []
            for private_value in (
                "soy",
                "sesame",
                "synthetic",
                reviewed["name"].lower(),
            ):
                assert private_value not in context_json.lower()
            return MealPlanProviderResult({"items": [selection()]})

    monkeypatch.setitem(
        app.dependency_overrides, get_meal_plan_generation_provider, Provider
    )
    response = await client.post(
        URL, headers=headers, json={**REQUEST, "meal_types": ["lunch"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["recipe_id"] == eligible["id"]
