import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_abuse import AuthAbuseAction, AuthAbuseDimension
from app.core.config import get_settings
from app.core.security import decode_access_token, normalize_auth_abuse_identifier
from app.db.session import get_db
from app.integrations.email_verification_mailer import EmailVerificationMailer
from app.integrations.openai_recipe_generation import OpenAIRecipeGenerationProvider
from app.integrations.password_reset_mailer import PasswordResetMailer
from app.integrations.recipe_generation import RecipeGenerationProvider
from app.integrations.smtp_email_verification_mailer import (
    SmtpEmailVerificationMailer,
)
from app.integrations.smtp_password_reset_mailer import SmtpPasswordResetMailer
from app.models.user import User
from app.repositories.users import UsersRepository
from app.services.auth_abuse import (
    AuthAbuseConfigurationError,
    AuthAbuseLimitExceeded,
    AuthAbuseProtectionService,
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
)

_AUTH_ABUSE_LIMIT_DETAIL = "Too many authentication requests. Please try again later."
_AUTH_ABUSE_UNAVAILABLE_DETAIL = "Authentication protection is unavailable"


def get_direct_client_ip(request: Request) -> str:
    """Use only the ASGI peer address.

    Forwarded headers remain untrusted until a deployment defines explicit
    trusted proxies. Container launch commands disable Uvicorn proxy parsing.
    """
    if request.client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_AUTH_ABUSE_UNAVAILABLE_DETAIL,
        )

    try:
        return normalize_auth_abuse_identifier(
            dimension=AuthAbuseDimension.IP,
            identifier=request.client.host,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_AUTH_ABUSE_UNAVAILABLE_DETAIL,
        ) from exc


async def enforce_auth_abuse_limit(
    *,
    db: AsyncSession,
    action: AuthAbuseAction,
    client_ip: str,
    email: str | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    identifiers = {
        AuthAbuseDimension.IP: client_ip,
    }
    if email is not None:
        identifiers[AuthAbuseDimension.EMAIL] = email
    if user_id is not None:
        identifiers[AuthAbuseDimension.USER] = str(user_id)

    service = AuthAbuseProtectionService(db)
    try:
        await service.enforce(
            action=action,
            identifiers=identifiers,
        )
    except AuthAbuseLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_AUTH_ABUSE_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except AuthAbuseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_AUTH_ABUSE_UNAVAILABLE_DETAIL,
        ) from exc


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


def get_email_verification_mailer() -> EmailVerificationMailer:
    settings = get_settings()

    host = (settings.smtp_host or "").strip()
    from_email = (settings.smtp_from_email or "").strip()
    verification_url_base = (settings.email_verification_url_base or "").strip()
    username = (settings.smtp_username or "").strip() or None
    password = None

    if settings.smtp_password is not None:
        password = settings.smtp_password.get_secret_value().strip() or None

    if not host or not from_email or not verification_url_base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is not configured",
        )

    try:
        from_email = str(TypeAdapter(EmailStr).validate_python(from_email))
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is not configured",
        ) from exc

    if (username is None) != (password is None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is not configured",
        )

    try:
        return SmtpEmailVerificationMailer(
            host=host,
            port=settings.smtp_port,
            username=username,
            password=password,
            from_email=from_email,
            starttls=settings.smtp_starttls,
            verification_url_base=verification_url_base,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is not configured",
        ) from exc


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
