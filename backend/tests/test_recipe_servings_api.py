"""Serving persistence, backward compatibility and whole-recipe consumer semantics."""

from decimal import Decimal
from uuid import UUID

import pytest

from app.schemas.recipe import RecipeUpdate
from app.services.recipes import RecipesService
from tests.test_ai_recipe_save_api import (
    AI_RECIPE_SAVE_URL,
    RECIPES_URL,
    create_authenticated_user,
    create_ingredient,
    save_payload,
)


@pytest.mark.parametrize("servings", [2, 12])
async def test_recipe_servings_survives_reads_and_partial_updates(client, servings):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={"title": "Portions", "instructions": "Mix.", "servings": servings},
    )
    assert response.status_code == 201
    recipe = response.json()
    assert recipe["servings"] == servings
    url = f"{RECIPES_URL}/{recipe['id']}"
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["servings"] == servings
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert [(item["id"], item["servings"]) for item in response.json()] == [
        (recipe["id"], servings)
    ]
    response = await client.patch(url, headers=headers, json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["servings"] == servings
    replacement = 12 if servings == 2 else 2
    response = await client.patch(url, headers=headers, json={"servings": replacement})
    assert response.status_code == 200
    assert response.json()["servings"] == replacement
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["servings"] == replacement


async def test_legacy_recipe_request_defaults_servings_to_one(client):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={"title": "Legacy request", "instructions": "Mix."},
    )
    assert response.status_code == 201
    recipe = response.json()
    assert recipe["servings"] == 1
    response = await client.get(f"{RECIPES_URL}/{recipe['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["servings"] == 1


@pytest.mark.parametrize("value", [None, True, "2", 1.5, 0, 13])
async def test_invalid_servings_write_leaves_recipe_and_collection_unchanged(
    client, value
):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, servings=2)
    payload["instructions"] = "Mix."
    response = await client.post(RECIPES_URL, headers=headers, json=payload)
    assert response.status_code == 201
    original = response.json()
    url = f"{RECIPES_URL}/{original['id']}"
    response = await client.patch(
        url, headers=headers, json={"title": "Must not persist", "servings": value}
    )
    assert response.status_code == 422
    for endpoint in [RECIPES_URL, AI_RECIPE_SAVE_URL]:
        invalid = save_payload(ingredient, servings=value)
        if endpoint == RECIPES_URL:
            invalid["instructions"] = "Mix."
        response = await client.post(endpoint, headers=headers, json=invalid)
        assert response.status_code == 422
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json() == original
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [original]


async def test_servings_patch_is_owner_scoped(client):
    _, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=owner,
        json={"title": "Private portions", "instructions": "Mix.", "servings": 2},
    )
    assert response.status_code == 201
    original = response.json()
    url = f"{RECIPES_URL}/{original['id']}"
    response = await client.patch(url, headers=other, json={"servings": 12})
    assert response.status_code == 404
    response = await client.get(url, headers=owner)
    assert response.status_code == 200
    assert response.json() == original


async def test_commit_failure_rolls_back_flushed_servings_and_title(
    client, async_session_maker, monkeypatch
):
    user, headers = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={"title": "Before failed commit", "instructions": "Mix.", "servings": 2},
    )
    assert response.status_code == 201
    original = response.json()
    async with async_session_maker() as db:

        async def fail_commit():
            await db.flush()
            raise RuntimeError("injected servings commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected servings commit failure"):
            await RecipesService(db).update_recipe(
                user_id=UUID(user["id"]),
                recipe_id=UUID(original["id"]),
                data=RecipeUpdate(servings=12, title="Must roll back"),
            )
    response = await client.get(f"{RECIPES_URL}/{original['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == original


@pytest.mark.parametrize("servings", [None, 2, 12])
async def test_ai_save_retains_servings_and_whole_recipe_nutrition(client, servings):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient)
    if servings is not None:
        payload["servings"] = servings
    response = await client.post(AI_RECIPE_SAVE_URL, headers=headers, json=payload)
    assert response.status_code == 201
    recipe = response.json()
    assert recipe["servings"] == (1 if servings is None else servings)
    assert Decimal(recipe["total_calories"]) == Decimal("330.00")
    assert Decimal(recipe["recipe_ingredients"][0]["quantity_g"]) == 200
    response = await client.get(f"{RECIPES_URL}/{recipe['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == recipe


async def test_servings_changes_do_not_scale_planner_totals_or_shopping_mass(client):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, servings=2)
    payload["instructions"] = "Mix."
    response = await client.post(RECIPES_URL, headers=headers, json=payload)
    assert response.status_code == 201
    recipe = response.json()
    response = await client.post(
        "/api/v1/meal-plans",
        headers=headers,
        json={
            "title": "Whole recipe plan",
            "start_date": "2026-11-16",
            "end_date": "2026-11-22",
            "items": [
                {
                    "recipe_id": recipe["id"],
                    "planned_date": "2026-11-16",
                    "meal_type": "dinner",
                }
            ],
        },
    )
    assert response.status_code == 201
    plan_url = f"/api/v1/meal-plans/{response.json()['id']}"
    before = {}
    for path in ["summary", "daily-summary", "shopping-list"]:
        response = await client.get(f"{plan_url}/{path}", headers=headers)
        assert response.status_code == 200
        before[path] = response.json()
    assert Decimal(before["summary"]["total_calories"]) == Decimal("330.00")
    assert Decimal(before["daily-summary"][0]["total_calories"]) == Decimal("330.00")
    assert Decimal(before["shopping-list"][0]["required_quantity_g"]) == 200
    response = await client.patch(
        f"{RECIPES_URL}/{recipe['id']}", headers=headers, json={"servings": 12}
    )
    assert response.status_code == 200
    after = response.json()
    assert after["servings"] == 12
    for field in ["total_calories", "total_protein_g", "total_carbs_g", "total_fat_g"]:
        assert after[field] == recipe[field]
    assert after["recipe_ingredients"] == recipe["recipe_ingredients"]
    for path, expected in before.items():
        response = await client.get(f"{plan_url}/{path}", headers=headers)
        assert response.status_code == 200
        assert response.json() == expected
