"""Declared metadata boundaries; pure schemas/calculators, no database fixtures."""

from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai_recipe import AIRecipeGenerationRequest
from app.schemas.ingredient import (
    IngredientCreate,
    IngredientUpdate,
    NutritionValueCreate,
    NutritionValueRead,
)
from app.schemas.user_nutrition_profile import UserNutritionProfileRead
from app.services.ai_recipe_context import AIRecipeContextBuilder
from app.services.gram_nutrition import NUTRIENTS
from app.services.pantry_nutrition import PantryNutritionCalculator
from app.services.recipe_nutrition import RecipeNutritionCalculator


SOURCE = {"source_name": "Synthetic label v1", "source_reference": "qa-pack:rev-1"}


@pytest.mark.parametrize("schema", [IngredientCreate, IngredientUpdate])
@pytest.mark.parametrize("field", ["source_name", "source_reference"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        " \t\n\u00a0\u2003",
        0,
        1.5,
        True,
        False,
        [],
        {},
        b"label",
        "a\x00b",
        "\ud800",
        "\udfff",
    ],
)
def test_invalid_source_text(schema, field, value):
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "name": "Synthetic",
                "nutrition_value": {"calories": "1", **SOURCE, field: value},
            }
        )


@pytest.mark.parametrize(
    "field,limit", [("source_name", 255), ("source_reference", 1000)]
)
def test_unicode_trim_length_and_storage_validity(field, limit):
    # Character limits, not bytes; no casefolding/NFC or ingredient identity.
    value = "é" * (limit - 3) + "A\u0301🍲"
    assert len(value) == limit
    result = NutritionValueCreate(calories="1", **{**SOURCE, field: f"\u2003{value}\t"})
    assert getattr(result, field) == value
    with pytest.raises(ValidationError):
        NutritionValueCreate(calories="1", **{**SOURCE, field: value + "x"})


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"source_name": None},
        {"source_reference": None},
        {"source_name": None, "source_reference": None},
        {"source_name": "Label"},
    ],
)
def test_nullable_pair_and_numeric_defaults(values):
    source = NutritionValueCreate(calories="100", **values)
    assert source.source_name == values.get("source_name")
    assert source.source_reference is None
    assert source.calories == 100 and source.portion_g == 100
    assert source.protein_g == source.carbs_g == source.fat_g == 0


@pytest.mark.parametrize(
    "values",
    [
        {"source_reference": "record"},
        {"source_name": None, "source_reference": "record"},
        SOURCE,
    ],
)
def test_pair_and_required_calories(values):
    with pytest.raises(ValidationError):
        NutritionValueCreate(**values)
    if values != SOURCE:
        with pytest.raises(ValidationError):
            NutritionValueCreate(calories="1", **values)


@pytest.mark.parametrize(
    "metadata", [{}, {"source_name": None, "source_reference": None}, SOURCE]
)
@pytest.mark.parametrize(
    "calories,portion,projection,total",
    [
        ("100", "50", "200.00", "250.00"),
        ("0", "100", "0.00", "0.00"),
        ("0.01", "999999.99", "0.00", "0.00"),
    ],
)
def test_read_and_aggregate_semantics_ignore_declaration(
    metadata, calories, portion, projection, total
):
    source = NutritionValueRead(
        id=uuid4(),
        ingredient_id=uuid4(),
        calories=calories,
        portion_g=portion,
        **metadata,
    )
    response = source.model_dump(mode="json")
    assert response["source_name"] == metadata.get("source_name")
    assert response["source_reference"] == metadata.get("source_reference")
    assert set(response["per_100g"]) == set(NUTRIENTS)
    assert response["per_100g"]["calories"] == projection
    assert source.calories == Decimal(calories)
    items = [NS(quantity_g=Decimal("125"), ingredient=NS(nutrition_value=source))]
    assert (
        str(
            RecipeNutritionCalculator()
            .calculate_from_recipe(NS(recipe_ingredients=items))
            .total_calories
        )
        == total
    )
    pantry = PantryNutritionCalculator().calculate_from_pantry_items(items)
    if calories == "0.01":
        assert pantry.total_calories > 0


@pytest.mark.parametrize("field", SOURCE)
def test_generation_request_forbids_source(field):
    with pytest.raises(ValidationError):
        AIRecipeGenerationRequest.model_validate({field: SOURCE[field]})


def test_provider_context_never_includes_catalog_nutrition_or_declaration():
    builder = AIRecipeContextBuilder()
    context = builder.build_context(
        request=AIRecipeGenerationRequest(),
        nutrition_profile=UserNutritionProfileRead.default(),
        pantry_items=[
            NS(
                id=uuid4(),
                quantity_g=Decimal("125"),
                ingredient=NS(
                    name="Synthetic",
                    nutrition_value=NS(calories=Decimal("100"), **SOURCE),
                ),
            )
        ],
    )
    assert context.model_dump(mode="json")["pantry_items"] == [
        {"name": "Synthetic", "available_quantity_g": "125", "unit": "g"}
    ]
    request = builder.build_provider_request(context=context)
    assert "source_name" not in request.input and "qa-pack" not in request.input
