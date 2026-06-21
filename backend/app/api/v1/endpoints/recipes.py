import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.recipe import RecipeCreate, RecipeRead, RecipeUpdate
from app.services.recipes import RecipesService

router = APIRouter(prefix="/recipes", tags=["Recipes"])


@router.get("", response_model=list[RecipeRead])
async def list_current_user_recipes(
    search: str | None = Query(default=None, min_length=1),
    diet_type: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    return await service.list_user_recipes(
        user_id=current_user.id,
        search=search,
        diet_type=diet_type,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=RecipeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_recipe(
    payload: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    return await service.create_recipe(
        user_id=current_user.id,
        data=payload,
    )


@router.get("/{recipe_id}", response_model=RecipeRead)
async def get_recipe(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    return await service.get_recipe(
        user_id=current_user.id,
        recipe_id=recipe_id,
    )


@router.patch("/{recipe_id}", response_model=RecipeRead)
async def update_recipe(
    recipe_id: uuid.UUID,
    payload: RecipeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    return await service.update_recipe(
        user_id=current_user.id,
        recipe_id=recipe_id,
        data=payload,
    )


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_recipe(
    recipe_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    await service.delete_recipe(
        user_id=current_user.id,
        recipe_id=recipe_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
