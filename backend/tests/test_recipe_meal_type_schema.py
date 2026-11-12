"""Optional recipe classification; independent of planner slot validation."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai_recipe import AIRecipeSavePreviewRequest
from app.schemas.recipe import RecipeCreate, RecipeUpdate

SCHEMAS = [RecipeCreate, RecipeUpdate, AIRecipeSavePreviewRequest]


def payload_for(schema):
    if schema is RecipeUpdate:
        return {}
    payload = {"title": "Meal type", "instructions": "Mix."}
    if schema is AIRecipeSavePreviewRequest:
        payload["instructions"] = ["Mix."]
        payload["ingredients"] = [{"ingredient_id": uuid4(), "quantity_g": "100"}]
    return payload


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        (" \t\n\u00a0", None),
        ("  DiNnEr  ", "dinner"),
        ("BRUNCH", "brunch"),
        ("Поздний УЖИН", "поздний ужин"),
        ("X" * 100, "x" * 100),
    ],
)
def test_meal_type_normalization_and_custom_labels(schema, value, expected):
    request = schema.model_validate({**payload_for(schema), "meal_type": value})
    assert request.meal_type == expected


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize(
    "value", [True, 1, 1.5, [], {}, "x" * 101, "\u0130" * 51, "bad\x00label", "\ud800"]
)
def test_nontext_overlength_and_unstorable_labels_are_rejected(schema, value):
    with pytest.raises(ValidationError):
        schema.model_validate({**payload_for(schema), "meal_type": value})


@pytest.mark.parametrize("schema", SCHEMAS)
def test_omission_is_unknown_and_patch_does_not_clear(schema):
    request = schema.model_validate(payload_for(schema))
    assert request.meal_type is None
    assert "meal_type" not in request.model_dump(exclude_unset=True)


@pytest.mark.parametrize("value", [None, "", "  DiNnEr  ", "brunch"])
def test_ai_save_forwards_normalized_classification_without_changing_recipe(value):
    request = AIRecipeSavePreviewRequest.model_validate(
        {**payload_for(AIRecipeSavePreviewRequest), "meal_type": value, "servings": 2}
    )
    recipe = request.to_recipe_create()
    assert recipe.meal_type == request.meal_type
    assert recipe.servings == 2
    assert recipe.instructions == "1. Mix."
    assert recipe.ingredients[0].quantity_g == 100
