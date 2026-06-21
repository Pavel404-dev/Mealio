import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.exceptions import DuplicateResourceError
from app.schemas.user import UserCreate, UserUpdate


class UsersRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))

        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        normalized_email = email.strip().lower()

        result = await self.db.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        )

        return result.scalar_one_or_none()

    async def create(self, data: UserCreate) -> User:
        user = User(
            email=str(data.email).strip().lower(),
            full_name=data.full_name,
        )

        self.db.add(user)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()

            raise DuplicateResourceError("User with this email already exists") from exc

        created_user = await self.get_by_id(user.id)

        if created_user is None:
            raise RuntimeError("Created user was not found")

        return created_user

    async def create_registered(
        self,
        *,
        email: str,
        full_name: str | None,
        password_hash: str,
    ) -> User:
        user = User(
            email=email.strip().lower(),
            full_name=full_name,
            password_hash=password_hash,
        )

        self.db.add(user)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()

            raise DuplicateResourceError("User with this email already exists") from exc

        created_user = await self.get_by_id(user.id)

        if created_user is None:
            raise RuntimeError("Created user was not found")

        return created_user

    async def update(
        self,
        *,
        user: User,
        data: UserUpdate,
    ) -> User:
        update_data = data.model_dump(exclude_unset=True)

        if "email" in update_data:
            user.email = str(update_data["email"]).strip().lower()

        if "full_name" in update_data:
            user.full_name = update_data["full_name"]

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()

            raise DuplicateResourceError("User with this email already exists") from exc

        await self.db.refresh(user)

        return user
