from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.shopping_list import ShoppingListItemRead
from app.services.shopping_list import ShoppingListService

router = APIRouter(
    prefix="/shopping-list",
    tags=["Shopping List"],
)


@router.get("", response_model=list[ShoppingListItemRead])
async def get_current_user_combined_shopping_list(
    from_date: date = Query(...),
    to_date: date = Query(...),
    meal_type: str | None = Query(default=None, min_length=1, max_length=50),
    subtract_pantry: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ShoppingListService(db)

    return await service.get_current_user_combined_shopping_list(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        meal_type=meal_type,
        subtract_pantry=subtract_pantry,
    )
