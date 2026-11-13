"""Strict persisted preparation time with backward-compatible unknown values."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai_recipe import AIRecipeSavePreviewRequest, GeneratedRecipeData
from app.schemas.recipe import RecipeCreate, RecipeUpdate

SCHEMAS = [RecipeCreate, RecipeUpdate, AIRecipeSavePreviewRequest]


def payload_for(schema):
    if schema is RecipeUpdate:
        return {}
    payload = {"title": "Preparation time", "instructions": "Mix."}
    if schema is AIRecipeSavePreviewRequest:
        payload["instructions"] = ["Mix."]
        payload["ingredients"] = [{"ingredient_id": uuid4(), "quantity_g": "100"}]
    return payload


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize("minutes", [None, 1, 45, 480])
def test_prep_time_accepts_unknown_and_integer_boundaries(schema, minutes):
    request = schema.model_validate(
        {**payload_for(schema), "prep_time_minutes": minutes}
    )
    assert request.prep_time_minutes == minutes


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize(
    "value", [True, False, "45", "", 45.0, 1.5, 0, -1, 481, [], {}]
)
def test_prep_time_rejects_coercion_and_out_of_range_values(schema, value):
    with pytest.raises(ValidationError):
        schema.model_validate({**payload_for(schema), "prep_time_minutes": value})


@pytest.mark.parametrize("schema", SCHEMAS)
def test_omission_remains_unknown_and_does_not_clear_patch(schema):
    request = schema.model_validate(payload_for(schema))
    assert request.prep_time_minutes is None
    assert "prep_time_minutes" not in request.model_dump(exclude_unset=True)


@pytest.mark.parametrize("minutes", [None, 1, 45, 480])
def test_ai_save_forwards_duration_without_scaling_the_recipe(minutes):
    request = AIRecipeSavePreviewRequest.model_validate(
        {
            **payload_for(AIRecipeSavePreviewRequest),
            "prep_time_minutes": minutes,
            "servings": 2,
            "meal_type": "dinner",
        }
    )
    saved = request.to_recipe_create()
    assert saved.prep_time_minutes == minutes
    assert saved.servings == 2
    assert saved.meal_type == "dinner"
    assert saved.ingredients[0].quantity_g == 100
    assert saved.instructions == "1. Mix."


def test_existing_generated_preview_duration_survives_save_conversion():
    preview = GeneratedRecipeData(
        title="Preview",
        servings=2,
        prep_time_minutes=30,
        ingredients=[{"name": "Synthetic ingredient", "quantity_g": "100"}],
        instructions=["Mix."],
    )
    payload = preview.model_dump(mode="json")
    payload["ingredients"] = [{"ingredient_id": uuid4(), "quantity_g": "100"}]
    assert (
        AIRecipeSavePreviewRequest.model_validate(payload)
        .to_recipe_create()
        .prep_time_minutes
        == 30
    )
