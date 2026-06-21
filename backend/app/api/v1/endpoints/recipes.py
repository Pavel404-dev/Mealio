import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.recipe import RecipeCreate, RecipeRead, RecipeUpdate
from app.services.recipes import RecipesService

router = APIRouter(prefix="/recipes", tags=["Recipes"])


@router.get("", response_model=list[RecipeRead])
async def list_recipes(
    search: str | None = Query(default=None, min_length=1),
    diet_type: str | None = Query(default=None, min_length=1),
    created_by_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)

    return await service.list_recipes(
        search=search,
        diet_type=diet_type,
        created_by_user_id=created_by_user_id,
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
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)
    return await service.create_recipe(payload)


@router.get("/{recipe_id}", response_model=RecipeRead)
async def get_recipe(
    recipe_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)
    return await service.get_recipe(recipe_id)


@router.patch("/{recipe_id}", response_model=RecipeRead)
async def update_recipe(
    recipe_id: uuid.UUID,
    payload: RecipeUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)
    return await service.update_recipe(recipe_id, payload)


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_recipe(
    recipe_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    service = RecipesService(db)
    await service.delete_recipe(recipe_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
