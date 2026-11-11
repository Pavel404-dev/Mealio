"""Serving count validation at the persisted recipe write boundaries."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai_recipe import AIRecipeSavePreviewRequest
from app.schemas.recipe import RecipeCreate, RecipeUpdate


def payload_for(schema):
    if schema is RecipeUpdate:
        return {}
    payload = {"title": "Serving count", "instructions": "Mix."}
    if schema is AIRecipeSavePreviewRequest:
        payload["instructions"] = ["Mix."]
        payload["ingredients"] = [{"ingredient_id": uuid4(), "quantity_g": "100"}]
    return payload


@pytest.mark.parametrize(
    "schema", [RecipeCreate, RecipeUpdate, AIRecipeSavePreviewRequest]
)
@pytest.mark.parametrize("value", [1, 2, 12])
def test_servings_accepts_integer_boundaries(schema, value):
    request = schema.model_validate({**payload_for(schema), "servings": value})
    assert request.servings == value


@pytest.mark.parametrize(
    "schema", [RecipeCreate, RecipeUpdate, AIRecipeSavePreviewRequest]
)
@pytest.mark.parametrize("value", [None, True, False, "2", 2.0, 1.5, 0, -1, 13, [], {}])
def test_servings_rejects_null_coercion_and_out_of_range_values(schema, value):
    with pytest.raises(ValidationError):
        schema.model_validate({**payload_for(schema), "servings": value})


@pytest.mark.parametrize("schema", [RecipeCreate, AIRecipeSavePreviewRequest])
def test_omitted_servings_defaults_to_one_for_legacy_requests(schema):
    request = schema.model_validate(payload_for(schema))
    assert request.servings == 1


def test_patch_omission_does_not_replace_servings():
    assert "servings" not in RecipeUpdate(title="Renamed").model_dump(
        exclude_unset=True
    )


@pytest.mark.parametrize("value", [None, 2, 12])
def test_ai_conversion_preserves_servings_and_ingredient_mass(value):
    payload = payload_for(AIRecipeSavePreviewRequest)
    if value is not None:
        payload["servings"] = value
    saved = AIRecipeSavePreviewRequest.model_validate(payload).to_recipe_create()
    assert saved.servings == (1 if value is None else value)
    assert saved.ingredients[0].quantity_g == 100
    assert saved.instructions == "1. Mix."
