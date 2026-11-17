"""Portions persisted through v2 and consumed by every existing aggregate."""

from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.main import app
from app.models.recipe import Recipe
from tests.test_meal_plans_api import create_authenticated_user
from tests.test_pantry_api import add_pantry_item
from tests.test_recipe_nutrition_totals_api import create_test_ingredient

V1 = "/api/v1/meal-plans"
V2 = "/api/v2/meal-plans"
CALENDAR = "/api/v1/meal-plan-items/calendar"
SHOPPING = "/api/v1/shopping-list"
DATES = {"from_date": "2026-11-17", "to_date": "2026-11-30"}
PROGRESS_DATES = {"start_date": DATES["from_date"], "end_date": DATES["to_date"]}


async def get_json(client, url, headers, **params):
    response = await client.get(url, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def ingredient(
    client, headers, *, calories="165", protein="31", carbs="0", fat="3.6"
):
    return await create_test_ingredient(
        client,
        headers=headers,
        name=f"Portion test ingredient {uuid4()}",
        nutrition_value={
            "portion_g": "100",
            "calories": calories,
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
        },
    )


async def recipe(client, headers, ingredient_id, *, servings=4, quantity="200"):
    response = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "title": "Portion test recipe",
            "instructions": "Mix.",
            "servings": servings,
            "ingredients": [{"ingredient_id": ingredient_id, "quantity_g": quantity}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def item(recipe_id, *, servings=None, meal_type="lunch", day="2026-11-17"):
    return {
        "recipe_id": recipe_id,
        "planned_date": day,
        "meal_type": meal_type,
        "planned_servings": servings,
    }


async def plan(client, headers, items, *, version=V2):
    response = await client.post(
        version,
        headers=headers,
        json={
            "title": "Portion plan",
            "start_date": DATES["from_date"],
            "end_date": DATES["to_date"],
            "items": items,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def assert_totals(row, calories, protein, carbs, fat):
    for key, value in zip(
        ("calories", "protein_g", "carbs_g", "fat_g"),
        (calories, protein, carbs, fat),
        strict=True,
    ):
        assert Decimal(row[f"total_{key}"]) == Decimal(value)


async def test_one_portion_reconciles_summary_progress_gaps_shopping_and_refill(client):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(client, headers)
    dish = await recipe(client, headers, component["id"])
    saved = await plan(client, headers, [item(dish["id"], servings="1")])
    assert Decimal(saved["items"][0]["planned_servings"]) == 1
    assert await get_json(client, f"{V2}/{saved['id']}", headers) == saved
    assert await get_json(client, V2, headers, search="Portion", **DATES) == [saved]
    summary = await get_json(client, f"{V1}/{saved['id']}/summary", headers)
    assert summary["items_count"] == 1
    assert_totals(summary, "82.50", "15.50", "0", "1.80")
    daily = await get_json(client, f"{V1}/{saved['id']}/daily-summary", headers)
    assert len(daily) == 1
    assert_totals(daily[0], "82.50", "15.50", "0", "1.80")
    response = await client.patch(
        "/api/v1/user-preferences/nutrition",
        headers=headers,
        json={
            "daily_calories_target": 1000,
            "daily_protein_target_g": 100,
            "daily_carbs_target_g": 100,
            "daily_fat_target_g": 100,
        },
    )
    assert response.status_code == 200
    progress = await get_json(
        client, f"{CALENDAR}/nutrition-progress", headers, **PROGRESS_DATES
    )
    assert_totals(progress[0], "82.50", "15.50", "0", "1.80")
    assert Decimal(progress[0]["remaining_calories"]) == Decimal("917.50")
    gaps = await get_json(
        client, f"{CALENDAR}/nutrition-gaps", headers, **PROGRESS_DATES
    )
    assert Decimal(gaps[0]["calories_gap"]) == Decimal("917.50")
    assert gaps[0]["calories_status"] == "under"

    await add_pantry_item(
        client, headers=headers, ingredient_id=component["id"], quantity_g="12.50"
    )
    per_plan = await get_json(
        client,
        f"{V1}/{saved['id']}/shopping-list",
        headers,
        **DATES,
        subtract_pantry=True,
    )
    combined = await get_json(client, SHOPPING, headers, **DATES, subtract_pantry=True)
    assert combined == per_plan and len(combined) == 1
    assert Decimal(combined[0]["required_quantity_g"]) == 50
    assert Decimal(combined[0]["pantry_quantity_g"]) == Decimal("12.50")
    assert Decimal(combined[0]["missing_quantity_g"]) == Decimal("37.50")
    response = await client.post(
        f"{SHOPPING}/add-missing-to-pantry", headers=headers, params=DATES
    )
    assert response.status_code == 200
    refill = response.json()
    assert refill["updated_items_count"] == 1
    assert Decimal(refill["items"][0]["added_quantity_g"]) == Decimal("37.50")
    assert Decimal(refill["items"][0]["new_pantry_quantity_g"]) == 50
    assert (
        Decimal(
            (await get_json(client, SHOPPING, headers, **DATES, subtract_pantry=True))[
                0
            ]["missing_quantity_g"]
        )
        == 0
    )
    response = await client.post(
        f"{SHOPPING}/add-missing-to-pantry", headers=headers, params=DATES
    )
    assert response.status_code == 200 and response.json()["updated_items_count"] == 0


async def test_add_item_and_count_only_patch_persist_fraction_and_explicit_null(client):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(client, headers)
    dish = await recipe(client, headers, component["id"])
    saved = await plan(client, headers, [])
    response = await client.post(
        f"{V2}/{saved['id']}/items",
        headers=headers,
        json=item(dish["id"], servings="1.25"),
    )
    assert response.status_code == 201
    assigned = response.json()
    assert Decimal(assigned["planned_servings"]) == Decimal("1.25")
    item_url = f"{V2}/{saved['id']}/items/{assigned['id']}"
    for count, expected in [("0.01", "0.83"), (12, "990"), (None, "330")]:
        response = await client.patch(
            item_url, headers=headers, json={"planned_servings": count}
        )
        assert response.status_code == 200
        assert response.json()["planned_servings"] == (
            None if count is None else str(count)
        )
        restored = await get_json(client, f"{V2}/{saved['id']}", headers)
        assert restored["items"] == [response.json()]
        summary = await get_json(client, f"{V1}/{saved['id']}/summary", headers)
        assert Decimal(summary["total_calories"]) == Decimal(expected)


async def test_live_recipe_edits_and_v1_patch_preserve_explicit_or_whole_semantics(
    client,
):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(client, headers)
    dish = await recipe(client, headers, component["id"])
    saved = await plan(
        client,
        headers,
        [item(dish["id"], servings=1), item(dish["id"], meal_type="dinner")],
    )
    assigned = next(
        row for row in saved["items"] if row["planned_servings"] is not None
    )
    item_path = f"/{saved['id']}/items/{assigned['id']}"
    response = await client.patch(
        V1 + item_path,
        headers=headers,
        json={"meal_type": "brunch", "planned_servings": 12},
    )
    assert response.status_code == 200 and "planned_servings" not in response.json()
    response = await client.patch(V2 + item_path, headers=headers, json={})
    assert (
        response.status_code == 200
        and Decimal(response.json()["planned_servings"]) == 1
    )
    assert response.json()["meal_type"] == "brunch"
    for patch, expected_calories, expected_grams in [
        ({"servings": 2}, "495", "300"),
        (
            {"ingredients": [{"ingredient_id": component["id"], "quantity_g": "400"}]},
            "990",
            "600",
        ),
    ]:
        response = await client.patch(
            f"/api/v1/recipes/{dish['id']}", headers=headers, json=patch
        )
        assert response.status_code == 200
        totals = await get_json(client, f"{V1}/{saved['id']}/summary", headers)
        assert Decimal(totals["total_calories"]) == Decimal(expected_calories)
        shopping = await get_json(client, f"{V1}/{saved['id']}/shopping-list", headers)
        assert Decimal(shopping[0]["required_quantity_g"]) == Decimal(expected_grams)
    response = await client.patch(
        V2 + item_path, headers=headers, json={"planned_servings": None}
    )
    assert response.status_code == 200 and response.json()["planned_servings"] is None
    totals = await get_json(client, f"{V1}/{saved['id']}/summary", headers)
    assert Decimal(totals["total_calories"]) == 1320
    # A v1 create ignores the unknown field and stays whole-recipe too.
    legacy = await plan(client, headers, [item(dish["id"], servings=1)], version=V1)
    assert "planned_servings" not in legacy["items"][0]
    assert (await get_json(client, f"{V2}/{legacy['id']}", headers))["items"][0][
        "planned_servings"
    ] is None
    assert (
        Decimal(
            (await get_json(client, f"{V1}/{legacy['id']}/summary", headers))[
                "total_calories"
            ]
        )
        == 660
    )


async def test_portion_write_failures_are_atomic_and_v2_reads_enforce_ownership(client):
    _, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    component = await ingredient(client, owner)
    dish = await recipe(client, owner, component["id"])
    foreign = await recipe(client, other, component["id"])
    saved = await plan(
        client,
        owner,
        [item(dish["id"], servings="0.5"), item(dish["id"], meal_type="dinner")],
    )
    assigned = next(
        row for row in saved["items"] if row["planned_servings"] is not None
    )
    item_url = f"{V2}/{saved['id']}/items/{assigned['id']}"
    for patch, status in [
        ({"planned_servings": "1.005", "planned_date": "2026-11-18"}, 422),
        ({"planned_servings": 2, "meal_type": "dinner"}, 409),
        ({"planned_servings": 2, "planned_date": "2026-12-01"}, 422),
        ({"planned_servings": 2, "recipe_id": foreign["id"]}, 404),
    ]:
        response = await client.patch(item_url, headers=owner, json=patch)
        assert response.status_code == status
        assert await get_json(client, f"{V2}/{saved['id']}", owner) == saved
    response = await client.post(
        V2,
        headers=owner,
        json={
            "title": "Invalid nested",
            "start_date": DATES["from_date"],
            "items": [
                item(dish["id"], servings=1),
                item(dish["id"], servings="12.001", meal_type="snack"),
            ],
        },
    )
    assert response.status_code == 422
    assert await get_json(client, V2, owner) == [saved]
    response = await client.post(
        f"{V2}/{saved['id']}/items",
        headers=owner,
        json=item(dish["id"], servings=True, meal_type="snack"),
    )
    assert response.status_code == 422
    response = await client.patch(item_url, headers=other, json={"planned_servings": 2})
    assert response.status_code == 404
    response = await client.get(f"{V2}/{saved['id']}", headers=other)
    assert response.status_code == 404
    assert await get_json(client, V2, other) == []
    assert await get_json(client, SHOPPING, other, **DATES) == []
    assert await get_json(client, V2, owner, search="absent") == []
    assert await get_json(client, V2, owner, offset=1) == []
    for params in [{"limit": 0}, {"from_date": "2026-11-19", "to_date": "2026-11-17"}]:
        response = await client.get(V2, headers=owner, params=params)
        assert response.status_code == 422
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as anonymous:
        for url in [V2, f"{V2}/{saved['id']}"]:
            assert (await anonymous.get(url)).status_code == 401


def rounded_fraction(value):
    # Independent oracle: exact rational to hundredths, ties away from zero.
    cents = value * 100
    rounded = (2 * abs(cents.numerator) + cents.denominator) // (2 * cents.denominator)
    return Decimal(rounded if value >= 0 else -rounded) / 100


@pytest.mark.parametrize(
    "yields,counts",
    [
        ([3, 3, 3], ["1", "1", "1"]),
        ([6, 3], ["1", "1"]),  # Exact half-cent only after adding unlike fractions.
        ([12], ["0.01"]),  # Demand rounds to zero and must not create pantry stock.
        (
            list(range(1, 13)),
            [
                "0.01",
                "0.5",
                "1.25",
                "12",
                "1",
                "2",
                "0.25",
                "3",
                "4",
                "0.02",
                "1",
                None,
            ],
        ),
    ],
)
async def test_exact_fractions_round_once_per_group_across_all_aggregates(
    client, yields, counts
):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(
        client, headers, calories="100", protein="100", carbs="100", fat="100"
    )
    assignments, expected_days = [], []
    for index, (yield_count, count) in enumerate(zip(yields, counts, strict=True)):
        dish = await recipe(
            client, headers, component["id"], servings=yield_count, quantity="0.01"
        )
        # First two cases share a day; all yields case checks daily group rounding.
        day = date(2026, 11, 17) + timedelta(days=index if len(yields) > 4 else 0)
        assignments.append(
            item(
                dish["id"],
                servings=count,
                day=day.isoformat(),
                meal_type=["breakfast", "lunch", "dinner", "snack"][index % 4],
            )
        )
        expected_days.append(
            (
                day.isoformat(),
                Fraction(1, 100)
                * (1 if count is None else Fraction(count) / yield_count),
            )
        )
    saved = await plan(client, headers, assignments)
    expected = rounded_fraction(sum((value for _, value in expected_days), Fraction(0)))
    summary = await get_json(client, f"{V1}/{saved['id']}/summary", headers)
    assert_totals(summary, expected, expected, expected, expected)
    daily = await get_json(client, f"{V1}/{saved['id']}/daily-summary", headers)
    progress = await get_json(
        client, f"{CALENDAR}/nutrition-progress", headers, **PROGRESS_DATES
    )
    for rows in [daily, progress]:
        for row in rows:
            amount = rounded_fraction(
                sum(
                    (value for day, value in expected_days if day == row["date"]),
                    Fraction(0),
                )
            )
            assert_totals(row, amount, amount, amount, amount)
    for url in [f"{V1}/{saved['id']}/shopping-list", SHOPPING]:
        shopping = await get_json(client, url, headers, **DATES)
        assert Decimal(shopping[0]["required_quantity_g"]) == expected
    response = await client.post(
        f"{SHOPPING}/add-missing-to-pantry", headers=headers, params=DATES
    )
    assert response.status_code == 200
    if expected:
        assert Decimal(response.json()["items"][0]["new_pantry_quantity_g"]) == expected
    else:
        assert response.json()["updated_items_count"] == 0
        assert response.json()["items"] == []


async def test_combined_plans_filters_legacy_signed_and_null_nutrition(
    client, db_session
):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(client, headers)
    dish = await recipe(client, headers, component["id"])
    first = await plan(client, headers, [item(dish["id"], servings="0.5")])
    await plan(
        client,
        headers,
        [item(dish["id"], servings="1.5", day="2026-11-18", meal_type="dinner")],
    )
    combined = await get_json(client, SHOPPING, headers, **DATES)
    assert Decimal(combined[0]["required_quantity_g"]) == 100
    filtered = await get_json(client, SHOPPING, headers, **DATES, meal_type=" LUNCH ")
    assert Decimal(filtered[0]["required_quantity_g"]) == 25
    filtered = await get_json(
        client, SHOPPING, headers, from_date="2026-11-18", to_date="2026-11-18"
    )
    assert Decimal(filtered[0]["required_quantity_g"]) == 75
    # Historical signed/unknown totals remain representable in v1 summaries.
    await db_session.execute(
        update(Recipe)
        .where(Recipe.id == UUID(dish["id"]))
        .values(
            total_calories=Decimal("-1"),
            total_protein_g=None,
            total_carbs_g=None,
            total_fat_g=None,
        )
    )
    await db_session.commit()
    summary = await get_json(client, f"{V1}/{first['id']}/summary", headers)
    assert_totals(summary, "-0.13", "0", "0", "0")


async def test_weighted_pantry_overflow_rejects_all_upserts(client):
    _, headers = await create_authenticated_user(client)
    component = await ingredient(
        client, headers, calories="0", protein="0", carbs="0", fat="0"
    )
    huge = await recipe(
        client, headers, component["id"], servings=1, quantity="10000000"
    )
    small = await ingredient(client, headers, calories="1")
    small_dish = await recipe(client, headers, small["id"], servings=1, quantity="10")
    await plan(
        client,
        headers,
        [
            item(huge["id"], servings=12),
            item(small_dish["id"], servings=1, meal_type="dinner"),
        ],
    )
    before = await get_json(client, "/api/v1/pantry", headers)
    shopping = await get_json(client, SHOPPING, headers, **DATES)
    assert max(Decimal(row["required_quantity_g"]) for row in shopping) == 120000000
    response = await client.post(
        f"{SHOPPING}/add-missing-to-pantry", headers=headers, params=DATES
    )
    assert response.status_code == 422
    assert await get_json(client, "/api/v1/pantry", headers) == before
