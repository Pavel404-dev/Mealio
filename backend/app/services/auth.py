from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.users import UsersRepository
from app.schemas.auth import UserRegister


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = UsersRepository(db)

    async def register_user(self, data: UserRegister):
        existing_user = await self.repository.get_by_email(
            str(data.email)
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        plain_password = data.password.get_secret_value()
        password_hash = hash_password(plain_password)

        try:
            return await self.repository.create_registered(
                email=str(data.email),
                full_name=data.full_name,
                password_hash=password_hash,
            )
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc