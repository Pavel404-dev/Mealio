from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_email_verification_mailer,
    get_password_reset_mailer,
)
from app.db.session import get_db
from app.integrations.email_verification_mailer import EmailVerificationMailer
from app.integrations.password_reset_mailer import PasswordResetMailer
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    EmailVerificationRequestResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
)
from app.schemas.user import UserRead, UserUpdate
from app.services.auth import AuthService
from app.services.users import UsersService


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

_EMAIL_VERIFICATION_REQUEST_MESSAGE = (
    "If verification is needed for that email, "
    "verification instructions have been sent."
)
_PASSWORD_RESET_REQUEST_MESSAGE = (
    "If an account with that email exists, password reset instructions have been sent."
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    payload: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    mailer: EmailVerificationMailer = Depends(get_email_verification_mailer),
):
    service = AuthService(db)
    result = await service.register_user(payload)

    background_tasks.add_task(
        mailer.send_email_verification,
        recipient_email=result.delivery.recipient_email,
        verification_token=result.delivery.verification_token,
    )

    return result.user


@router.post(
    "/login",
    response_model=TokenPairResponse,
)
async def login_user(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.login_user(payload)


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.refresh_tokens(payload)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout_user(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(db)

    await service.logout_session(payload)


@router.post(
    "/email-verification/request",
    response_model=EmailVerificationRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_email_verification(
    payload: EmailVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    mailer: EmailVerificationMailer = Depends(get_email_verification_mailer),
) -> EmailVerificationRequestResponse:
    service = AuthService(db)
    delivery = await service.request_email_verification(payload)

    if delivery is not None:
        background_tasks.add_task(
            mailer.send_email_verification,
            recipient_email=delivery.recipient_email,
            verification_token=delivery.verification_token,
        )

    return EmailVerificationRequestResponse(
        message=_EMAIL_VERIFICATION_REQUEST_MESSAGE,
    )


@router.post(
    "/email-verification/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def confirm_email_verification(
    payload: EmailVerificationConfirm,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(db)

    await service.confirm_email_verification(payload)


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    mailer: PasswordResetMailer = Depends(get_password_reset_mailer),
) -> PasswordResetRequestResponse:
    service = AuthService(db)
    delivery = await service.request_password_reset(payload)

    if delivery is not None:
        background_tasks.add_task(
            mailer.send_password_reset,
            recipient_email=delivery.recipient_email,
            reset_token=delivery.reset_token,
        )

    return PasswordResetRequestResponse(
        message=_PASSWORD_RESET_REQUEST_MESSAGE,
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(db)

    await service.confirm_password_reset(payload)


@router.get(
    "/me",
    response_model=UserRead,
)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch(
    "/me",
    response_model=UserRead,
)
async def update_current_user(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UsersService(db)

    return await service.update_user(
        user_id=current_user.id,
        data=payload,
    )
