import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.ingredient import IngredientRead
from app.schemas.storage_decimal import QuantityWrite


class PantryItemCreate(BaseModel):
    ingredient_id: uuid.UUID
    quantity_g: QuantityWrite
    expires_at: datetime | None = None


class PantryItemUpdate(BaseModel):
    quantity_g: QuantityWrite | None = None
    expires_at: datetime | None = None


class PantryItemRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity_g: Decimal
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ingredient: IngredientRead

    model_config = ConfigDict(from_attributes=True)


class PantryNutritionSummaryRead(BaseModel):
    items_count: int
    total_calories: Decimal
    total_protein_g: Decimal
    total_carbs_g: Decimal
    total_fat_g: Decimal

    model_config = ConfigDict(from_attributes=True)
