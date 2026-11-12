"""Persistence, atomic writes and independence from planner meal types."""

import json
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


@pytest.mark.parametrize("ai_save", [False, True])
@pytest.mark.parametrize(
    "value", [None, "", " \t\n", "  DiNnEr  ", "BRUNCH", "X" * 100]
)
async def test_manual_and_ai_save_persist_classification(client, ai_save, value):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, servings=2)
    if value is not None:
        payload["meal_type"] = value
    if not ai_save:
        payload["instructions"] = "Mix."
    response = await client.post(
        AI_RECIPE_SAVE_URL if ai_save else RECIPES_URL, headers=headers, json=payload
    )
    assert response.status_code == 201
    recipe = response.json()
    assert recipe["meal_type"] == ((value.strip().lower() or None) if value else None)
    assert recipe["servings"] == 2
    assert Decimal(recipe["total_calories"]) == Decimal("330.00")
    response = await client.get(f"{RECIPES_URL}/{recipe['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == recipe
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [recipe]


async def test_patch_omission_update_clear_and_invalid_atomicity(client):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={"title": "Before", "instructions": "Mix.", "meal_type": "dinner"},
    )
    assert response.status_code == 201
    url = f"{RECIPES_URL}/{response.json()['id']}"
    response = await client.patch(url, headers=headers, json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["meal_type"] == "dinner"
    for value, expected in [
        ("  LuNcH ", "lunch"),
        (None, None),
        ("brunch", "brunch"),
        (" \t", None),
    ]:
        response = await client.patch(url, headers=headers, json={"meal_type": value})
        assert response.status_code == 200
        assert response.json()["meal_type"] == expected
        read = await client.get(url, headers=headers)
        assert read.status_code == 200
        assert read.json() == response.json()
    original = response.json()
    for value in [True, 1, 1.5, [], {}, "x" * 101, "bad\x00label", "\ud800"]:
        response = await client.patch(
            url,
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps({"title": "Must not persist", "meal_type": value}),
        )
        assert response.status_code == 422
        # Validation fails before either title or metadata can be written.
        read = await client.get(url, headers=headers)
        assert read.status_code == 200
        assert read.json() == original


@pytest.mark.parametrize("value", [True, 1, 1.5, [], {}, "x" * 101, "bad\x00label"])
async def test_invalid_create_and_ai_save_leave_collection_unchanged(client, value):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, meal_type=value)
    for endpoint in [AI_RECIPE_SAVE_URL, RECIPES_URL]:
        if endpoint == RECIPES_URL:
            payload["instructions"] = "Mix."
        response = await client.post(endpoint, headers=headers, json=payload)
        assert response.status_code == 422
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_meal_type_is_owner_scoped_and_failed_commit_rolls_back(
    client, async_session_maker, monkeypatch
):
    user, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=owner,
        json={"title": "Private", "instructions": "Mix.", "meal_type": "dinner"},
    )
    assert response.status_code == 201
    original = response.json()
    url = f"{RECIPES_URL}/{original['id']}"
    for payload in [{"meal_type": "lunch"}, {"meal_type": None}]:
        response = await client.patch(url, headers=other, json=payload)
        assert response.status_code == 404
    response = await client.get(url, headers=other)
    assert response.status_code == 404
    response = await client.get(RECIPES_URL, headers=other)
    assert response.status_code == 200
    assert response.json() == []
    async with async_session_maker() as db:

        async def fail_commit():
            await db.flush()
            raise RuntimeError("injected meal type commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected meal type commit failure"):
            await RecipesService(db).update_recipe(
                user_id=UUID(user["id"]),
                recipe_id=UUID(original["id"]),
                data=RecipeUpdate(meal_type=None, title="Must roll back"),
            )
    response = await client.get(url, headers=owner)
    assert response.status_code == 200
    assert response.json() == original
    # A normal retry after rollback must still succeed.
    response = await client.patch(url, headers=owner, json={"meal_type": "lunch"})
    assert response.status_code == 200
    assert response.json()["meal_type"] == "lunch"


async def test_recipe_classification_does_not_reclassify_planner_slots(client):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            **save_payload(ingredient, servings=2, meal_type="dinner"),
            "instructions": "Mix.",
        },
    )
    assert response.status_code == 201
    recipe = response.json()
    response = await client.post(
        "/api/v1/meal-plans",
        headers=headers,
        json={
            "title": "Independent slots",
            "start_date": "2026-11-16",
            "end_date": "2026-11-22",
            "items": [
                {
                    "recipe_id": recipe["id"],
                    "planned_date": "2026-11-16",
                    "meal_type": "breakfast",
                }
            ],
        },
    )
    assert response.status_code == 201
    plan_url = f"/api/v1/meal-plans/{response.json()['id']}"
    before = {}
    for path in [
        "",
        "/summary",
        "/daily-summary",
        "/shopping-list?meal_type=breakfast",
        "/shopping-list?meal_type=dinner",
    ]:
        response = await client.get(f"{plan_url}{path}", headers=headers)
        assert response.status_code == 200
        before[path] = response.json()
    assert before[""]["items"][0]["meal_type"] == "breakfast"
    assert Decimal(before["/summary"]["total_calories"]) == Decimal("330.00")
    assert (
        Decimal(before["/shopping-list?meal_type=breakfast"][0]["required_quantity_g"])
        == 200
    )
    assert before["/shopping-list?meal_type=dinner"] == []
    for value in ["lunch", None]:
        response = await client.patch(
            f"{RECIPES_URL}/{recipe['id']}", headers=headers, json={"meal_type": value}
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["meal_type"] == value
        for field in [
            "servings",
            "total_calories",
            "total_protein_g",
            "total_carbs_g",
            "total_fat_g",
            "recipe_ingredients",
        ]:
            assert updated[field] == recipe[field]
        for path, expected in before.items():
            response = await client.get(f"{plan_url}{path}", headers=headers)
            assert response.status_code == 200
            assert response.json() == expected
