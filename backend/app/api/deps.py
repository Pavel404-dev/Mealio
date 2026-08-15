import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.integrations.openai_recipe_generation import OpenAIRecipeGenerationProvider
from app.integrations.password_reset_mailer import PasswordResetMailer
from app.integrations.recipe_generation import RecipeGenerationProvider
from app.integrations.smtp_password_reset_mailer import SmtpPasswordResetMailer
from app.models.user import User
from app.repositories.users import UsersRepository


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
)


def get_recipe_generation_provider() -> RecipeGenerationProvider:
    settings = get_settings()

    if settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI recipe generation is not configured",
        )

    api_key = settings.openai_api_key.get_secret_value().strip()
    model = settings.openai_model.strip()

    if not api_key or not model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI recipe generation is not configured",
        )

    return OpenAIRecipeGenerationProvider(
        api_key=api_key,
        model=model,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )


def get_password_reset_mailer() -> PasswordResetMailer:
    settings = get_settings()

    host = (settings.smtp_host or "").strip()
    from_email = (settings.smtp_from_email or "").strip()
    reset_url_base = (settings.password_reset_url_base or "").strip()
    username = (settings.smtp_username or "").strip() or None
    password = None

    if settings.smtp_password is not None:
        password = settings.smtp_password.get_secret_value().strip() or None

    if not host or not from_email or not reset_url_base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset delivery is not configured",
        )

    try:
        from_email = str(TypeAdapter(EmailStr).validate_python(from_email))
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset delivery is not configured",
        ) from exc

    if (username is None) != (password is None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset delivery is not configured",
        )

    try:
        return SmtpPasswordResetMailer(
            host=host,
            port=settings.smtp_port,
            username=username,
            password=password,
            from_email=from_email,
            starttls=settings.smtp_starttls,
            reset_url_base=reset_url_base,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset delivery is not configured",
        ) from exc


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")

        if subject is None:
            raise credentials_exception

        user_id = uuid.UUID(str(subject))

    except (InvalidTokenError, ValueError):
        raise credentials_exception

    repository = UsersRepository(db)
    user = await repository.get_by_id(user_id)

    if user is None:
        raise credentials_exception

    return user
