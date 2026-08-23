from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuthAbuseAction(str, Enum):
    LOGIN = "login"
    REGISTER = "register"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_CONFIRM = "password_reset_confirm"
    EMAIL_VERIFICATION_REQUEST = "email_verification_request"
    EMAIL_VERIFICATION_CONFIRM = "email_verification_confirm"


class AuthAbuseDimension(str, Enum):
    IP = "ip"
    EMAIL = "email"
    USER = "user"


class AuthAbusePolicy(BaseModel):
    action: AuthAbuseAction
    dimension: AuthAbuseDimension
    limit: int = Field(ge=1, le=10_000)
    window_seconds: int = Field(ge=1, le=86_400)

    model_config = ConfigDict(frozen=True)


def default_auth_abuse_policies() -> list[AuthAbusePolicy]:
    return [
        AuthAbusePolicy(
            action=AuthAbuseAction.LOGIN,
            dimension=AuthAbuseDimension.IP,
            limit=30,
            window_seconds=5 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.LOGIN,
            dimension=AuthAbuseDimension.EMAIL,
            limit=10,
            window_seconds=15 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.REGISTER,
            dimension=AuthAbuseDimension.IP,
            limit=10,
            window_seconds=15 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.REGISTER,
            dimension=AuthAbuseDimension.EMAIL,
            limit=3,
            window_seconds=60 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.PASSWORD_RESET_REQUEST,
            dimension=AuthAbuseDimension.IP,
            limit=10,
            window_seconds=60 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.PASSWORD_RESET_REQUEST,
            dimension=AuthAbuseDimension.EMAIL,
            limit=3,
            window_seconds=60 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.EMAIL_VERIFICATION_REQUEST,
            dimension=AuthAbuseDimension.IP,
            limit=10,
            window_seconds=60 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.EMAIL_VERIFICATION_REQUEST,
            dimension=AuthAbuseDimension.EMAIL,
            limit=3,
            window_seconds=60 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.PASSWORD_RESET_CONFIRM,
            dimension=AuthAbuseDimension.IP,
            limit=30,
            window_seconds=5 * 60,
        ),
        AuthAbusePolicy(
            action=AuthAbuseAction.EMAIL_VERIFICATION_CONFIRM,
            dimension=AuthAbuseDimension.IP,
            limit=30,
            window_seconds=5 * 60,
        ),
    ]


def required_auth_abuse_policy_keys() -> (
    set[tuple[AuthAbuseAction, AuthAbuseDimension]]
):
    return {
        (policy.action, policy.dimension) for policy in default_auth_abuse_policies()
    }
