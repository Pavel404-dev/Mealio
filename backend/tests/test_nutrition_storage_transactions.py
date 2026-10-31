"""W9 independent-session storage, rollback and controlled writer interleavings."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.ingredient import Ingredient, NutritionValue
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User
from app.repositories.ingredients import IngredientsRepository
from app.repositories.recipes import RecipesRepository
from app.schemas.ingredient import IngredientCreate, IngredientUpdate
from app.schemas.recipe import RecipeCreate, RecipeUpdate
from app.services.ingredients import IngredientsService
from app.services.recipes import RecipesService


def composition(ids, quantity="125"):
    return [{"ingredient_id": i, "quantity_g": quantity} for i in ids]


async def setup(maker):
    async with maker() as db:
        user = User(email=f"{uuid4()}@example.test")
        db.add(user)
        await db.commit()
        owner = user.id
        ids = []
        for i in range(3):
            ingredient = await IngredientsService(db).create_ingredient(
                IngredientCreate(
                    name=f"W9 {i}",
                    category="original",
                    nutrition_value={
                        "calories": "100.000",
                        "protein_g": "1.2300",
                        "portion_g": "50",
                    },
                )
            )
            ids.append(ingredient.id)
        recipes = []
        for members in (ids[:2], ids[:1], ids[2:]):
            recipe = await RecipesService(db).create_recipe(
                user_id=owner,
                data=RecipeCreate(
                    title="W9 recipe",
                    instructions="Mix",
                    ingredients=composition(members),
                ),
            )
            recipes.append(recipe.id)
    return owner, ids, recipes


async def snapshot(maker):
    async with maker() as db:
        ingredients = (
            await db.execute(
                select(
                    Ingredient.id,
                    Ingredient.name,
                    Ingredient.category,
                    NutritionValue.calories,
                    NutritionValue.protein_g,
                    NutritionValue.portion_g,
                )
                .join(NutritionValue)
                .order_by(Ingredient.id)
            )
        ).all()
        recipes = (
            await db.execute(
                select(
                    Recipe.id,
                    Recipe.title,
                    Recipe.total_calories,
                    Recipe.total_protein_g,
                    Recipe.total_carbs_g,
                    Recipe.total_fat_g,
                ).order_by(Recipe.id)
            )
        ).all()
        quantities = (
            await db.execute(
                select(
                    RecipeIngredient.recipe_id,
                    RecipeIngredient.ingredient_id,
                    RecipeIngredient.quantity_g,
                ).order_by(RecipeIngredient.recipe_id, RecipeIngredient.ingredient_id)
            )
        ).all()
        return ingredients, recipes, quantities


async def test_stored_values_and_unaffected_counterexample(async_session_maker):
    owner, ids, recipes = await setup(async_session_maker)
    before = await snapshot(async_session_maker)
    assert all(row[4] == Decimal("1.23") and row[5] == 50 for row in before[0])
    assert all(row[2] == 125 for row in before[2])
    assert dict((r[0], r[2]) for r in before[1])[recipes[1]] == Decimal("250.00")
    async with async_session_maker() as db:
        await IngredientsService(db).update_ingredient(
            ids[0],
            IngredientUpdate(nutrition_value={"calories": "200", "portion_g": "50"}),
        )
    after = await snapshot(async_session_maker)
    totals = {r[0]: r[2] for r in after[1]}
    assert totals == {
        recipes[0]: Decimal("750.00"),
        recipes[1]: Decimal("500.00"),
        recipes[2]: Decimal("250.00"),
    }
    assert next(r for r in before[1] if r[0] == recipes[2]) == next(
        r for r in after[1] if r[0] == recipes[2]
    )
    assert before[2] == after[2]


@pytest.mark.parametrize(
    "failure", ["overflow", "calculation", "partial_flush", "commit"]
)
async def test_patch_rolls_back_every_field_and_all_recipes(
    async_session_maker, monkeypatch, failure
):
    _, ids, recipes = await setup(async_session_maker)
    before = await snapshot(async_session_maker)
    async with async_session_maker() as db:
        service = IngredientsService(db)
        if failure == "calculation":
            original = service.nutrition_calculator.calculate_from_recipe
            calls = 0

            def calculate(recipe):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("injected recalculation failure")
                return original(recipe)

            monkeypatch.setattr(
                service.nutrition_calculator, "calculate_from_recipe", calculate
            )
        elif failure == "partial_flush":
            original = (
                service.recipes_repository.update_nutrition_totals_for_loaded_recipes
            )

            async def partial(*, recipes, recipe_totals):
                await original(recipes=recipes[:1], recipe_totals=recipe_totals)
                await db.flush()
                raise RuntimeError(
                    "injected persistence failure after first recipe flush"
                )

            monkeypatch.setattr(
                service.recipes_repository,
                "update_nutrition_totals_for_loaded_recipes",
                partial,
            )
        elif failure == "commit":

            async def fail_commit():
                await db.flush()
                raise RuntimeError("injected commit failure")

            monkeypatch.setattr(db, "commit", fail_commit)
        data = IngredientUpdate(
            name="W9 changed",
            category="changed",
            nutrition_value={
                "calories": "999999.99" if failure == "overflow" else "200",
                "portion_g": "0.01" if failure == "overflow" else "50",
            },
        )
        with pytest.raises(
            HTTPException if failure == "overflow" else RuntimeError
        ) as error:
            await service.update_ingredient(ids[0], data)
        if failure == "overflow":
            assert error.value.status_code == 422
    assert await snapshot(async_session_maker) == before


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_recipe_overflow_rolls_back_composition(async_session_maker, operation):
    owner, ids, recipes = await setup(async_session_maker)
    before = await snapshot(async_session_maker)
    async with async_session_maker() as db:
        service = RecipesService(db)
        data = dict(
            title="changed",
            instructions="changed",
            ingredients=composition(ids[:1], "99999999.99"),
        )
        with pytest.raises(HTTPException) as error:
            if operation == "create":
                await service.create_recipe(user_id=owner, data=RecipeCreate(**data))
            else:
                await service.update_recipe(
                    user_id=owner, recipe_id=recipes[0], data=RecipeUpdate(**data)
                )
        assert error.value.status_code == 422
    assert await snapshot(async_session_maker) == before


@pytest.mark.parametrize(
    "pair",
    [
        "two_nutrients",
        "create_then_nutrient",
        "nutrient_then_create",
        "replace_then_nutrient",
        "nutrient_then_replace",
    ],
)
async def test_concurrent_writers_refresh_after_wait(
    async_session_maker, monkeypatch, pair
):
    from app.services import nutrition_transaction as transaction_module

    owner, ids, recipes = await setup(async_session_maker)
    first_locked, release, second_started = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    original_lock = transaction_module.lock_nutrition_writes
    pids = {}
    retained = []

    async def gate(db):
        name = asyncio.current_task().get_name()
        pids[name] = await db.scalar(text("SELECT pg_backend_pid()"))
        if name == "second":
            second_started.set()
        await original_lock(db)
        if name == "first":
            first_locked.set()
            await asyncio.wait_for(release.wait(), 8)

    monkeypatch.setattr(transaction_module, "lock_nutrition_writes", gate)

    async def update_nutrient(db, ingredient_id, calories):
        await IngredientsService(db).update_ingredient(
            ingredient_id,
            IngredientUpdate(nutrition_value={"calories": calories, "portion_g": "50"}),
        )

    async def create(db):
        await RecipesService(db).create_recipe(
            user_id=owner,
            data=RecipeCreate(
                title="concurrent new",
                instructions="Mix",
                ingredients=composition(ids[:2]),
            ),
        )

    async def replace(db):
        await RecipesService(db).update_recipe(
            user_id=owner,
            recipe_id=recipes[0],
            data=RecipeUpdate(ingredients=composition([ids[0], ids[2]], "50")),
        )

    async def run(name):
        async with async_session_maker() as db:
            # Hold strong references to stale eager-loaded objects, including
            # nutrition and composition, before the second writer waits.
            if name == "second":
                retained.extend(
                    await RecipesRepository(db).list_by_ingredient_id(ids[0])
                )
                for i in ids:
                    retained.append(await IngredientsRepository(db).get_by_id(i))
            if pair == "two_nutrients":
                await update_nutrient(
                    db,
                    ids[0] if name == "first" else ids[1],
                    "200" if name == "first" else "300",
                )
            elif (pair.startswith("nutrient_then") and name == "first") or (
                not pair.startswith("nutrient_then") and name == "second"
            ):
                await update_nutrient(db, ids[0], "200")
            elif "create" in pair:
                await create(db)
            else:
                await replace(db)

    tasks = []
    try:
        async with asyncio.timeout(12):
            tasks.append(asyncio.create_task(run("first"), name="first"))
            await first_locked.wait()
            tasks.append(asyncio.create_task(run("second"), name="second"))
            await second_started.wait()
            async with async_session_maker() as observer:
                while True:
                    assert not tasks[1].done(), "Second writer must wait for the gate"
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["second"]}
                    )
                    if pids["first"] in blockers:
                        break
                    await asyncio.sleep(0.01)
            assert pids["first"] != pids["second"]
            release.set()
            await asyncio.gather(*tasks)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
    async with async_session_maker() as db:
        values = dict(
            (await db.execute(select(Recipe.id, Recipe.total_calories))).all()
        )
        if pair == "two_nutrients":
            assert values[recipes[0]] == Decimal("1250.00")
        elif "replace" in pair:
            assert values[recipes[0]] == Decimal("300.00")
            members = (
                (
                    await db.execute(
                        select(RecipeIngredient.ingredient_id).where(
                            RecipeIngredient.recipe_id == recipes[0]
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert set(members) == {ids[0], ids[2]}
        else:
            assert values[recipes[0]] == Decimal("750.00")
            new_total = await db.scalar(
                select(Recipe.total_calories).where(Recipe.title == "concurrent new")
            )
            assert new_total == Decimal("750.00")
        assert values[recipes[1]] == Decimal("500.00")
        assert values[recipes[2]] == Decimal("250.00")


async def test_refill_overflow_is_atomic(client, async_session_maker):
    from tests.test_pantry_refill_concurrency import (
        scenario,
        refill,
        snapshot as pantry_snapshot,
    )
    from app.models.ingredient import UserIngredient

    owner, headers, ingredients, _ = await scenario(client, count=2)
    # Synthetic stored demand, no nutrition calculations are involved in refill.
    async with async_session_maker() as db:
        rows = (await db.scalars(select(RecipeIngredient))).all()
        for item in rows:
            item.quantity_g = Decimal("99999999.99")
        await db.commit()
    before = await pantry_snapshot(async_session_maker, owner)
    response = await refill(client, headers, meal_type=None)
    assert response.status_code == 422
    assert await pantry_snapshot(async_session_maker, owner) == before
    async with async_session_maker() as db:
        assert (await db.scalars(select(UserIngredient))).all() == []
