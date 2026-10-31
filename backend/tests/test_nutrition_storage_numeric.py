"""Pure schema/calculation regressions: no database or application settings."""

from decimal import Decimal, DefaultContext, Inexact, ROUND_DOWN, localcontext
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.ingredient import NutritionValueCreate, NutritionValueRead
from app.schemas.recipe import RecipeIngredientCreate, RecipeIngredientRead
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate
from app.schemas.ai_recipe import AIRecipeSaveIngredient
from app.services.recipe_nutrition import RecipeNutritionCalculator
from app.services.pantry_nutrition import PantryNutritionCalculator


@pytest.mark.parametrize(
    "value",
    [
        "1.234",
        "999999.999",
        "1000000",
        "1e99",
        "1e-99",
        True,
        False,
        "NaN",
        "sNaN",
        "Infinity",
        "-1",
        "1.23000000000000000000000000001",
    ],
)
@pytest.mark.parametrize("field", ["calories", "protein_g", "carbs_g", "fat_g"])
def test_nutrient_write_rejects_lossy_values(value, field):
    with pytest.raises(ValidationError):
        NutritionValueCreate.model_validate({"calories": "1", field: value})


@pytest.mark.parametrize(
    "schema",
    [
        RecipeIngredientCreate,
        PantryItemCreate,
        PantryItemUpdate,
        AIRecipeSaveIngredient,
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        "0.004",
        "1.234",
        "100000000",
        "99999999.999",
        "0",
        "-1",
        True,
        False,
        "NaN",
        "sNaN",
        "Infinity",
        "1e-99",
    ],
)
def test_quantity_write_rejects_lossy_values(schema, value):
    with pytest.raises(ValidationError):
        schema.model_validate({"ingredient_id": uuid4(), "quantity_g": value})


@pytest.mark.parametrize("value", ["0.01", "1.2300", "12300e-4", "1E+2", "999999.99"])
def test_exact_forms_and_defaults(value):
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_DOWN
        nutrient = NutritionValueCreate(calories=value)
        quantity = RecipeIngredientCreate(ingredient_id=uuid4(), quantity_g=value)
    assert nutrient.calories == quantity.quantity_g == Decimal(value)
    assert nutrient.protein_g == nutrient.carbs_g == nutrient.fat_g == 0
    assert nutrient.portion_g == 100
    assert isinstance(nutrient.model_dump(mode="json")["calories"], str)


def test_read_does_not_inherit_new_write_restrictions():
    assert NutritionValueRead(
        id=uuid4(), ingredient_id=uuid4(), calories="1.234"
    ).calories == Decimal("1.234")
    assert RecipeIngredientRead(
        id=uuid4(), recipe_id=uuid4(), ingredient_id=uuid4(), quantity_g="0.004"
    ).quantity_g == Decimal("0.004")


def rows(calories="100", portion="50", quantity="125", count=1):
    return [
        NS(
            quantity_g=Decimal(quantity),
            ingredient=NS(
                nutrition_value=NS(
                    calories=Decimal(calories),
                    protein_g=Decimal("0"),
                    carbs_g=Decimal("0"),
                    fat_g=Decimal("0"),
                    portion_g=Decimal(portion),
                )
            ),
        )
        for _ in range(count)
    ]


@pytest.mark.parametrize("count", [1, 2])
def test_half_ties_aggregate_before_rounding(count):
    items = rows("1", "2", "0.01", count)
    totals = RecipeNutritionCalculator().calculate_from_recipe(
        NS(recipe_ingredients=items)
    )
    assert totals.total_calories == Decimal("0.01")
    assert totals.total_calories.as_tuple().exponent == -2
    pantry = PantryNutritionCalculator().calculate_from_pantry_items(items)
    assert pantry.total_calories == Decimal("0.005") * count


def test_non100_portion_and_context_independence():
    items = rows()
    repeating = rows("1", "3", "1")
    expected = PantryNutritionCalculator().calculate_from_pantry_items(repeating)
    old_default = DefaultContext.copy()
    try:
        DefaultContext.prec = 2
        DefaultContext.rounding = ROUND_DOWN
        DefaultContext.traps[Inexact] = True
        DefaultContext.Emax = 1
        DefaultContext.Emin = -1
        DefaultContext.clamp = 1
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.rounding = ROUND_DOWN
            ctx.Emax = 1
            ctx.Emin = -1
            ctx.clamp = 1
            for signal in ctx.traps:
                ctx.traps[signal] = True
            result = RecipeNutritionCalculator().calculate_from_recipe(
                NS(recipe_ingredients=items)
            )
            assert result.total_calories == Decimal("250.00")
            assert (
                PantryNutritionCalculator().calculate_from_pantry_items(repeating)
                == expected
            )
            assert RecipeNutritionCalculator().calculate_from_recipe(
                NS(recipe_ingredients=repeating)
            ).total_calories == Decimal("0.33")
    finally:
        DefaultContext.prec = old_default.prec
        DefaultContext.rounding = old_default.rounding
        DefaultContext.traps = old_default.traps
        DefaultContext.Emax = old_default.Emax
        DefaultContext.Emin = old_default.Emin
        DefaultContext.clamp = old_default.clamp
    assert items[0].ingredient.nutrition_value.portion_g == 50


def test_final_rounding_overflow():
    # Exactly 99999999.995 before rounding; each raw input fits its storage.
    items = rows("1", "1", "99999999.99") + rows("1", "2", "0.01")
    with pytest.raises(HTTPException) as error:
        RecipeNutritionCalculator().calculate_from_recipe(NS(recipe_ingredients=items))
    assert error.value.status_code == 422


def test_missing_nutrition_still_contributes_zero():
    items = [NS(quantity_g=Decimal("1"), ingredient=NS(nutrition_value=None))]
    assert (
        RecipeNutritionCalculator()
        .calculate_from_recipe(NS(recipe_ingredients=items))
        .total_calories
        == 0
    )
    assert (
        PantryNutritionCalculator().calculate_from_pantry_items(items).items_count == 1
    )


@pytest.mark.parametrize(
    "count,portion,expected",
    [(3, "6", "0.01"), (7, "14", "0.01"), (1, "200.01", "0.00"), (1, "199.99", "0.01")],
)
def test_repeating_ratios_around_and_exactly_at_half_ties(count, portion, expected):
    quantity = "0.01" if count > 1 else "1"
    result = RecipeNutritionCalculator().calculate_from_recipe(
        NS(recipe_ingredients=rows("1", portion, quantity, count))
    )
    assert result.total_calories == Decimal(expected)


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
        "nutrition_value",
    ],
)
@pytest.mark.parametrize("level", ["root", "ingredient"])
@pytest.mark.parametrize("boundary", ["generated", "save"])
def test_ai_boundaries_reject_nutrient_injection(field, level, boundary):
    from app.schemas.ai_recipe import GeneratedRecipeData, AIRecipeSavePreviewRequest

    payload = dict(
        title="Preview", instructions=["Mix"], ingredients=[dict(quantity_g="1")]
    )
    if boundary == "generated":
        schema = GeneratedRecipeData
        payload.update(servings=1, prep_time_minutes=1)
        payload["ingredients"][0]["name"] = "Rice"
    else:
        schema = AIRecipeSavePreviewRequest
        payload["ingredients"][0]["ingredient_id"] = uuid4()
    target = payload if level == "root" else payload["ingredients"][0]
    target[field] = "42"
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_generated_mass_is_not_silently_rounded_at_save():
    from app.schemas.ai_recipe import GeneratedRecipeIngredient

    preview = GeneratedRecipeIngredient(name="Rice", quantity_g="0.004")
    assert preview.quantity_g == Decimal("0.004")
    with pytest.raises(ValidationError):
        AIRecipeSaveIngredient(ingredient_id=uuid4(), quantity_g=preview.quantity_g)


@pytest.mark.parametrize(
    "value", ["0", "0.0000", "999999.9900", "99999999.9900", "1E-2"]
)
def test_write_boundaries(value):
    quantity_data = dict(ingredient_id=uuid4(), quantity_g=value)
    if Decimal(value) == 0:
        assert NutritionValueCreate(calories=value).calories == 0
        with pytest.raises(ValidationError):
            RecipeIngredientCreate(**quantity_data)
    else:
        assert RecipeIngredientCreate(**quantity_data).quantity_g == Decimal(value)
        if Decimal(value) <= Decimal("999999.99"):
            assert NutritionValueCreate(calories=value).calories == Decimal(value)
        else:
            with pytest.raises(ValidationError):
                NutritionValueCreate(calories=value)


@pytest.mark.parametrize("value", ["0E+999999999", "0E-999999999", "-0.000000"])
def test_zero_exponents_are_canonicalized_without_rounding(value):
    assert NutritionValueCreate(calories=value).calories.as_tuple().exponent == 0


def test_precision_validation_does_not_use_ambient_rounding():
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        with pytest.raises(ValidationError):
            NutritionValueCreate(calories="1.23000000000000000000000000001")
        with pytest.raises(ValidationError):
            RecipeIngredientCreate(
                ingredient_id=uuid4(), quantity_g="1.23000000000000000000000000001"
            )


def test_final_rounding_safe_counterexample():
    items = rows("1", "1", "99999999.99") + rows("0.80", "2", "0.01")
    assert RecipeNutritionCalculator().calculate_from_recipe(
        NS(recipe_ingredients=items)
    ).total_calories == Decimal("99999999.99")
