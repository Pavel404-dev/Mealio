import uuid

from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeIngredientCreate, RecipeNutritionTotals
from app.services.gram_nutrition import aggregate_grams


class RecipeNutritionCalculator:
    def calculate_from_ingredient_inputs(
        self,
        *,
        ingredients: list[RecipeIngredientCreate],
        ingredients_by_id: dict[uuid.UUID, Ingredient],
    ) -> RecipeNutritionTotals:
        return RecipeNutritionTotals(
            **aggregate_grams(
                (
                    (
                        item.quantity_g,
                        ingredient.nutrition_value
                        if (ingredient := ingredients_by_id.get(item.ingredient_id))
                        is not None
                        else None,
                    )
                    for item in ingredients
                ),
                recipe=True,
            )
        )

    def calculate_from_recipe(self, recipe: Recipe) -> RecipeNutritionTotals:
        return RecipeNutritionTotals(
            **aggregate_grams(
                (
                    (
                        item.quantity_g,
                        item.ingredient.nutrition_value
                        if item.ingredient is not None
                        else None,
                    )
                    for item in recipe.recipe_ingredients
                ),
                recipe=True,
            )
        )
