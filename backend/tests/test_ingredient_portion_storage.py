"""Metadata-created PostgreSQL checks, separate from actual Alembic upgrades."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.ingredient import Ingredient, NutritionValue


@pytest.mark.parametrize("writer", ["sql", "orm"])
@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize(
    "portion, sqlstate",
    [
        ("0", "23514"),
        ("-1", "23514"),
        ("0.001", "23514"),
        ("NaN", "23514"),
        ("Infinity", "22003"),
        ("-Infinity", "22003"),
        ("1000000", "22003"),
    ],
)
async def test_direct_invalid_portion_cannot_persist(
    async_session_maker,
    writer,
    operation,
    portion,
    sqlstate,
):
    ingredient_id, nutrition_id = uuid4(), uuid4()
    async with async_session_maker() as session:
        session.add(Ingredient(id=ingredient_id, name="F3 direct write"))
        await session.flush()
        if operation == "update":
            session.add(
                NutritionValue(
                    id=nutrition_id,
                    ingredient_id=ingredient_id,
                    calories=Decimal("1"),
                    portion_g=Decimal("100"),
                )
            )
        await session.commit()

    observed = None
    async with async_session_maker() as session:
        try:
            if writer == "orm":
                if operation == "insert":
                    session.add(
                        NutritionValue(
                            id=nutrition_id,
                            ingredient_id=ingredient_id,
                            calories=Decimal("1"),
                            portion_g=Decimal(portion),
                        )
                    )
                else:
                    row = await session.get(NutritionValue, nutrition_id)
                    row.portion_g = Decimal(portion)
                await session.flush()
            elif operation == "insert":
                await session.execute(
                    text(
                        "INSERT INTO nutrition_values (id, ingredient_id, calories, portion_g) "
                        "VALUES (:id, :ingredient, 1, CAST(:portion AS numeric))"
                    ),
                    {
                        "id": nutrition_id,
                        "ingredient": ingredient_id,
                        "portion": portion,
                    },
                )
            else:
                await session.execute(
                    text(
                        "UPDATE nutrition_values SET portion_g = CAST(:portion AS numeric) WHERE id = :id"
                    ),
                    {"id": nutrition_id, "portion": portion},
                )
        except DBAPIError as error:
            observed = getattr(error.orig, "sqlstate", None)
        finally:
            # Even the vulnerable baseline must not commit an invalid direct write.
            await session.rollback()
    print(
        {
            "writer": writer,
            "operation": operation,
            "portion": portion,
            "sqlstate": observed,
        }
    )
    async with async_session_maker() as session:
        value = await session.scalar(
            select(NutritionValue.portion_g).where(NutritionValue.id == nutrition_id)
        )
        assert value == (Decimal("100") if operation == "update" else None)
    assert observed == sqlstate


@pytest.mark.parametrize("portion", ["0.01", "100.000", "999999.99"])
async def test_direct_valid_portion_survives_new_connection(
    async_session_maker, portion
):
    ingredient_id = uuid4()
    async with async_session_maker() as session:
        session.add(Ingredient(id=ingredient_id, name="F3 direct valid"))
        await session.flush()
        session.add(
            NutritionValue(
                ingredient_id=ingredient_id,
                calories=Decimal("1"),
                portion_g=Decimal(portion),
            )
        )
        await session.commit()
    async with async_session_maker() as session:
        value = await session.scalar(
            select(NutritionValue.portion_g).where(
                NutritionValue.ingredient_id == ingredient_id
            )
        )
        assert value == Decimal(portion)
