import uuid
from decimal import Decimal

from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeIngredientCreate, RecipeNutritionTotals


class RecipeNutritionCalculator:
    def calculate_from_ingredient_inputs(
        self,
        *,
        ingredients: list[RecipeIngredientCreate],
        ingredients_by_id: dict[uuid.UUID, Ingredient],
    ) -> RecipeNutritionTotals:
        total_calories = Decimal("0")
        total_protein_g = Decimal("0")
        total_carbs_g = Decimal("0")
        total_fat_g = Decimal("0")

        for recipe_ingredient in ingredients:
            ingredient = ingredients_by_id.get(recipe_ingredient.ingredient_id)

            if ingredient is None or ingredient.nutrition_value is None:
                continue

            nutrition_value = ingredient.nutrition_value

            if nutrition_value.portion_g <= 0:
                continue

            factor = recipe_ingredient.quantity_g / nutrition_value.portion_g

            total_calories += nutrition_value.calories * factor
            total_protein_g += nutrition_value.protein_g * factor
            total_carbs_g += nutrition_value.carbs_g * factor
            total_fat_g += nutrition_value.fat_g * factor

        return RecipeNutritionTotals(
            total_calories=total_calories,
            total_protein_g=total_protein_g,
            total_carbs_g=total_carbs_g,
            total_fat_g=total_fat_g,
        )

    def calculate_from_recipe(self, recipe: Recipe) -> RecipeNutritionTotals:
        total_calories = Decimal("0")
        total_protein_g = Decimal("0")
        total_carbs_g = Decimal("0")
        total_fat_g = Decimal("0")

        for recipe_ingredient in recipe.recipe_ingredients:
            ingredient = recipe_ingredient.ingredient

            if ingredient is None or ingredient.nutrition_value is None:
                continue

            nutrition_value = ingredient.nutrition_value

            if nutrition_value.portion_g <= 0:
                continue

            factor = recipe_ingredient.quantity_g / nutrition_value.portion_g

            total_calories += nutrition_value.calories * factor
            total_protein_g += nutrition_value.protein_g * factor
            total_carbs_g += nutrition_value.carbs_g * factor
            total_fat_g += nutrition_value.fat_g * factor

        return RecipeNutritionTotals(
            total_calories=total_calories,
            total_protein_g=total_protein_g,
            total_carbs_g=total_carbs_g,
            total_fat_g=total_fat_g,
        )
