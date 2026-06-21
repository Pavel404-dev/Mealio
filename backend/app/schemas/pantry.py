import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ingredient import IngredientRead


class PantryItemCreate(BaseModel):
    ingredient_id: uuid.UUID
    quantity_g: Decimal = Field(..., gt=0)
    expires_at: datetime | None = None


class PantryItemUpdate(BaseModel):
    quantity_g: Decimal | None = Field(default=None, gt=0)
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
