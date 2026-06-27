import uuid
from decimal import Decimal

from pydantic import BaseModel


class ShoppingListItemRead(BaseModel):
    ingredient_id: uuid.UUID
    ingredient_name: str
    ingredient_category: str | None
    required_quantity_g: Decimal
    pantry_quantity_g: Decimal | None = None
    missing_quantity_g: Decimal | None = None
