"""W8 regressions: behavior assertions also run against the pre-fix app."""

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.models.ingredient import Ingredient, NutritionValue
from app.repositories import ingredients as repository_module
from app.repositories.ingredients import IngredientsRepository
from app.schemas.ingredient import IngredientCreate
from app.services.ingredients import IngredientsService
from app.services import nutrition_transaction as transaction_module
from tests.test_ingredient_portion_api import create_dependencies, fresh_state
from tests.test_ingredients_api import create_authenticated_user

URL = "/api/v1/ingredients"


async def test_fold_duplicate_and_safe_counterexamples(client):
    _, headers = await create_authenticated_user(client)
    for name in ["Straße", "Chicken Breast", "Chicken Thigh", "Cafe", "Café"]:
        response = await client.post(URL, headers=headers, json={"name": name})
        assert response.status_code == 201
    duplicate = await client.post(URL, headers=headers, json={"name": " STRASSE "})
    assert duplicate.status_code == 409


async def test_literal_percent_search(client):
    _, headers = await create_authenticated_user(client)
    for name in ["100% cacao", "ordinary cacao"]:
        assert (
            await client.post(URL, headers=headers, json={"name": name})
        ).status_code == 201
    response = await client.get(URL, params={"search": "%"})
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["100% cacao"]


async def test_concurrent_equivalent_creates_between_users(client, monkeypatch):
    headers = [(await create_authenticated_user(client))[1] for _ in range(2)]
    original = IngredientsRepository.get_by_name
    barrier = asyncio.Barrier(2)

    async def synchronized_lookup(self, name):
        result = await original(self, name)
        async with asyncio.timeout(10):
            await barrier.wait()
        return result

    monkeypatch.setattr(IngredientsRepository, "get_by_name", synchronized_lookup)
    async with asyncio.timeout(15):
        responses = await asyncio.gather(
            *[
                client.post(URL, headers=h, json={"name": name})
                for h, name in zip(headers, ["Tomato", "TOMATO"], strict=True)
            ]
        )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert len((await client.get(URL)).json()) == 1


@pytest.mark.parametrize("kind", ["rename_rename", "create_rename"])
async def test_concurrent_rename_conflicts_rollback_without_recalculation(
    client, async_session_maker, monkeypatch, kind
):
    headers = [(await create_authenticated_user(client))[1] for _ in range(2)]
    originals = []
    for i in range(2):
        response = await client.post(
            URL,
            headers=headers[i],
            json={
                "name": f"Before {i}",
                "category": "before",
                "nutrition_value": {"calories": "10", "portion_g": "50"},
            },
        )
        assert response.status_code == 201
        originals.append((await client.get(f"{URL}/{response.json()['id']}")).json())
    barrier = asyncio.Barrier(2)
    original_lookup = IngredientsRepository.get_by_name
    observed = []
    original_classifier = repository_module.is_ingredient_name_conflict

    async def lookup(self, name):
        result = await original_lookup(self, name)
        if kind == "create_rename":
            # Create does not take the nutrition gate: retain the W8 witness
            # that both lookups miss and the database resolves the conflict.
            async with asyncio.timeout(10):
                await barrier.wait()
        return result

    if kind == "rename_rename":
        original_lock = transaction_module.lock_nutrition_writes

        async def synchronized_lock(db):
            # W9 serializes PATCH before reading mutable state. Synchronizing
            # after lookup would deadlock the test itself behind that gate.
            async with asyncio.timeout(10):
                await barrier.wait()
            await original_lock(db)

        monkeypatch.setattr(
            transaction_module, "lock_nutrition_writes", synchronized_lock
        )

    def classify(error):
        cause = error.orig.__cause__
        observed.append((cause.sqlstate, cause.constraint_name))
        return original_classifier(error)

    recalculate = AsyncMock()
    monkeypatch.setattr(IngredientsRepository, "get_by_name", lookup)
    monkeypatch.setattr(repository_module, "is_ingredient_name_conflict", classify)
    monkeypatch.setattr(
        IngredientsService, "_recalculate_recipes_using_ingredient", recalculate
    )
    paths = [f"{URL}/{row['id']}" for row in originals]
    methods = ["PATCH", "PATCH"]
    if kind == "create_rename":
        paths[0], methods[0] = URL, "POST"
    async with asyncio.timeout(15):
        responses = await asyncio.gather(
            *[
                client.request(
                    method,
                    path,
                    headers=auth,
                    json={
                        "name": name,
                        "category": "changed",
                        "nutrition_value": {"calories": "99"},
                    },
                )
                for method, path, auth, name in zip(
                    methods, paths, headers, ["Race", "RACE"], strict=True
                )
            ]
        )
    assert sum(r.status_code == 409 for r in responses) == 1
    assert sum(r.status_code in (200, 201) for r in responses) == 1
    # The second serialized PATCH must see the committed name and reject it
    # before mutation; create/PATCH still exercises the database race mapping.
    assert observed == (
        [] if kind == "rename_rename" else [("23505", "ux_ingredients_identity_v1")]
    )
    for i, response in enumerate(responses):
        if response.status_code == 409:
            assert (
                await client.get(f"{URL}/{originals[i]['id']}")
            ).json() == originals[i]
            assert all(
                call.args != (UUID(originals[i]["id"]),)
                for call in recalculate.await_args_list
            )
    async with async_session_maker() as session:
        rows = (await session.execute(select(Ingredient.name))).scalars().all()
    assert sum(name in ("Race", "RACE") for name in rows) == 1


async def test_label_edit_preserves_references_and_conflicting_patch_rolls_back(
    client, async_session_maker, monkeypatch
):
    _, headers = await create_authenticated_user(client)
    _, other_headers = await create_authenticated_user(client)
    ingredient, recipe = await create_dependencies(client, headers, other_headers)
    assert (
        await client.post(URL, headers=headers, json={"name": "Straße"})
    ).status_code == 201
    before = await fresh_state(async_session_maker)
    recalculate = AsyncMock()
    monkeypatch.setattr(
        IngredientsService, "_recalculate_recipes_using_ingredient", recalculate
    )
    response = await client.patch(
        f"{URL}/{ingredient}", headers=headers, json={"name": "Corrected label"}
    )
    assert response.status_code == 200 and response.json()["id"] == ingredient
    after = await fresh_state(async_session_maker)
    for table in before:
        if table != "ingredients":
            assert after[table] == before[table]
    assert {r["user_id"] for r in after["user_ingredients"]} == {
        r["user_id"] for r in before["user_ingredients"]
    }
    assert (
        await client.get(f"/api/v1/recipes/{recipe}", headers=other_headers)
    ).status_code == 404
    response = await client.patch(
        f"{URL}/{ingredient}",
        headers=headers,
        json={
            "name": " STRASSE ",
            "category": "wrong",
            "nutrition_value": {"calories": "900"},
        },
    )
    assert response.status_code == 409
    assert await fresh_state(async_session_maker) == after
    recalculate.assert_not_awaited()


@pytest.mark.parametrize(
    "name", ["\U0001d160" * 255, "\U0010ffff", "\ue000", "\U000105d2\u0307", "\uffff"]
)
async def test_unicode_api_and_asyncpg_roundtrip(client, async_session_maker, name):
    _, headers = await create_authenticated_user(client)
    response = await client.post(URL, headers=headers, json={"name": name})
    assert response.status_code == 201
    assert response.json()["name"] == name
    ingredient_id = UUID(response.json()["id"])
    async with async_session_maker() as session:
        assert (
            await session.scalar(
                select(Ingredient.name).where(Ingredient.id == ingredient_id)
            )
            == name
        )
    assert (await client.get(f"{URL}/{ingredient_id}")).json()["name"] == name
    matches = await client.post(
        "/api/v1/recipes/ai/ingredient-match-suggestions",
        headers=headers,
        json={"ingredient_names": [name]},
    )
    assert matches.status_code == 200
    assert matches.json()["results"][0]["exact_match"]["ingredient_id"] == str(
        ingredient_id
    )


@pytest.mark.parametrize(
    "name", ["\x00", "a\ud800", "\udfff", "\x1c\x1f", "\U0001d160" * 256]
)
async def test_invalid_name_rejected_before_database_binding(client, name):
    _, headers = await create_authenticated_user(client)
    for path, payload in [
        (URL, {"name": name}),
        (
            "/api/v1/recipes/ai/ingredient-match-suggestions",
            {"ingredient_names": [name]},
        ),
    ]:
        response = await client.post(
            path,
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps(payload),
        )
        assert response.status_code == 422
        assert "input" not in response.text
    assert (await client.get(URL)).json() == []


async def test_trim_before_length_checks_and_literal_ordered_search(client):
    _, headers = await create_authenticated_user(client)
    names = ["Chicken Breast", "100%", "under_score", "a\\b", "Cafe", "Café"]
    for name in names:
        assert (
            await client.post(URL, headers=headers, json={"name": name})
        ).status_code == 201
    response = await client.post(
        URL, headers=headers, json={"name": "\x1c" + "x" * 255 + "\x1f"}
    )
    assert response.status_code == 201 and response.json()["name"] == "x" * 255
    for query, expected in [
        ("  chicken   breast  ", ["Chicken Breast"]),
        ("%", ["100%"]),
        ("_", ["under_score"]),
        ("\\", ["a\\b"]),
        ("Cafe\u0301", ["Café"]),
        ("x" * 1000, []),
    ]:
        response = await client.get(URL, params={"search": query})
        assert response.status_code == 200
        assert [r["name"] for r in response.json()] == expected
    full = (await client.get(URL)).json()
    assert [r["name"] for r in full] == sorted(
        [*names, "x" * 255], key=lambda s: s.encode()
    )
    assert (await client.get(URL, params={"search": "\x1c\t \u00a0"})).json() == full
    pages = []
    for offset in range(0, len(full), 2):
        pages.extend(
            (await client.get(URL, params={"offset": offset, "limit": 2})).json()
        )
    assert pages == full
    for params in [
        {"search": ""},
        {"search": "\x00"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ]:
        assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.parametrize(
    "names",
    [
        ["Straße", "STRASSE"],
        ["Café", "Cafe\u0301"],
        ["Chicken Breast", " chicken\t breast "],
    ],
)
async def test_exact_duplicates_keep_validation_response_shape(client, names):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        "/api/v1/recipes/ai/ingredient-match-suggestions",
        headers=headers,
        json={"ingredient_names": names},
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", "ingredient_names"],
                "msg": "Value error, Ingredient names must be unique",
                "ctx": {"error": {}},
            }
        ]
    }


async def test_unrelated_unique_violation_is_not_a_name_conflict(
    db_session, monkeypatch
):
    repository = IngredientsRepository(db_session)
    first = await repository.create(
        IngredientCreate(name="First", nutrition_value={"calories": "1"})
    )
    nutrition_id = first.nutrition_value.id

    def duplicate_primary_key(mapper, connection, target):
        target.id = nutrition_id

    event.listen(NutritionValue, "before_insert", duplicate_primary_key)
    try:
        with pytest.raises(IntegrityError) as failure:
            await repository.create(
                IngredientCreate(name="Second", nutrition_value={"calories": "2"})
            )
    finally:
        event.remove(NutritionValue, "before_insert", duplicate_primary_key)
    cause = failure.value.orig.__cause__
    assert (
        cause.sqlstate == "23505" and cause.constraint_name == "nutrition_values_pkey"
    )
    assert await repository.get_by_name("Second") is None
    assert (await repository.get_by_name("First")).nutrition_value.calories == Decimal(
        "1"
    )
