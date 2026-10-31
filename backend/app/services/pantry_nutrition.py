from app.models.ingredient import UserIngredient
from app.schemas.pantry import PantryNutritionSummaryRead
from app.services.gram_nutrition import aggregate_grams


class PantryNutritionCalculator:
    def calculate_from_pantry_items(
        self,
        pantry_items: list[UserIngredient],
    ) -> PantryNutritionSummaryRead:
        return PantryNutritionSummaryRead(
            items_count=len(pantry_items),
            **aggregate_grams(
                (
                    (
                        item.quantity_g,
                        item.ingredient.nutrition_value
                        if item.ingredient is not None
                        else None,
                    )
                    for item in pantry_items
                ),
                recipe=False,
            ),
        )
