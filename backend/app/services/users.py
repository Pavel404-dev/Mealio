import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.exceptions import DuplicateResourceError
from app.repositories.users import UsersRepository
from app.schemas.user import UserCreate, UserUpdate


class UsersService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = UsersRepository(db)

    async def get_user(self, user_id: uuid.UUID):
        user = await self.repository.get_by_id(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    async def create_user(self, data: UserCreate):
        existing_user = await self.repository.get_by_email(
            str(data.email)
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        try:
            return await self.repository.create(data)
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    async def update_user(
            self,
            user_id: uuid.UUID,
            data: UserUpdate,
    ):
        user = await self.get_user(user_id)
        update_data = data.model_dump(exclude_unset=True)

        if "email" in update_data:
            existing_user = await self.repository.get_by_email(
                str(update_data["email"])
            )

            if (
                    existing_user is not None
                    and existing_user.id != user.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User with this email already exists",
                )

        try:
            return await self.repository.update(
                user=user,
                data=data,
            )
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc