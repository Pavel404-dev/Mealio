from decimal import Decimal

from app.models.ingredient import UserIngredient
from app.schemas.pantry import PantryNutritionSummaryRead


class PantryNutritionCalculator:
    def calculate_from_pantry_items(
        self,
        pantry_items: list[UserIngredient],
    ) -> PantryNutritionSummaryRead:
        total_calories = Decimal("0")
        total_protein_g = Decimal("0")
        total_carbs_g = Decimal("0")
        total_fat_g = Decimal("0")

        for pantry_item in pantry_items:
            ingredient = pantry_item.ingredient

            if ingredient is None or ingredient.nutrition_value is None:
                continue

            nutrition_value = ingredient.nutrition_value

            if nutrition_value.portion_g <= 0:
                continue

            factor = pantry_item.quantity_g / nutrition_value.portion_g

            total_calories += nutrition_value.calories * factor
            total_protein_g += nutrition_value.protein_g * factor
            total_carbs_g += nutrition_value.carbs_g * factor
            total_fat_g += nutrition_value.fat_g * factor

        return PantryNutritionSummaryRead(
            items_count=len(pantry_items),
            total_calories=total_calories,
            total_protein_g=total_protein_g,
            total_carbs_g=total_carbs_g,
            total_fat_g=total_fat_g,
        )
