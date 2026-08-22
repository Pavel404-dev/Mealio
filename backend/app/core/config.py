from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.auth_abuse import (
    AuthAbusePolicy,
    default_auth_abuse_policies,
    required_auth_abuse_policy_keys,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Mealio Backend API"
    app_version: str = "0.1.0"

    database_url: str

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365)

    email_verification_token_expire_hours: int = Field(default=24, ge=1, le=168)
    email_verification_url_base: str | None = None
    password_reset_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    password_reset_url_base: str | None = None

    email_otp_pepper: SecretStr | None = Field(default=None, min_length=32)
    email_otp_expire_minutes: int = Field(default=10, ge=1, le=30)
    email_otp_max_attempts: int = Field(default=5, ge=1, le=10)
    email_otp_resend_cooldown_seconds: int = Field(default=60, ge=1, le=3600)
    email_otp_max_deliveries_per_window: int = Field(default=5, ge=1, le=20)

    auth_abuse_pepper: SecretStr = Field(min_length=32)
    auth_abuse_policies: list[AuthAbusePolicy] = Field(
        default_factory=default_auth_abuse_policies,
        min_length=1,
        max_length=50,
    )

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True

    openai_api_key: SecretStr | None = None
    openai_model: str = Field(
        default="gpt-5.6-luna",
        min_length=1,
        max_length=100,
    )
    ai_request_timeout_seconds: float = Field(default=30, gt=0, le=120)

    @field_validator("email_otp_pepper", mode="before")
    @classmethod
    def normalize_empty_email_otp_pepper(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("auth_abuse_pepper", mode="before")
    @classmethod
    def reject_blank_auth_abuse_pepper(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("AUTH_ABUSE_PEPPER must not be blank")
        return value

    @model_validator(mode="after")
    def validate_security_secrets_and_auth_abuse_policies(self) -> Self:
        if (
            self.email_otp_pepper is not None
            and self.email_otp_pepper.get_secret_value() == self.jwt_secret_key
        ):
            raise ValueError("EMAIL_OTP_PEPPER must be different from JWT_SECRET_KEY")

        abuse_pepper = self.auth_abuse_pepper.get_secret_value()
        if abuse_pepper == self.jwt_secret_key:
            raise ValueError("AUTH_ABUSE_PEPPER must be different from JWT_SECRET_KEY")
        if (
            self.email_otp_pepper is not None
            and abuse_pepper == self.email_otp_pepper.get_secret_value()
        ):
            raise ValueError(
                "AUTH_ABUSE_PEPPER must be different from EMAIL_OTP_PEPPER"
            )

        policy_keys = [
            (policy.action, policy.dimension) for policy in self.auth_abuse_policies
        ]
        if len(policy_keys) != len(set(policy_keys)):
            raise ValueError("AUTH_ABUSE_POLICIES contains duplicate action/dimension")

        missing_policy_keys = required_auth_abuse_policy_keys() - set(policy_keys)
        if missing_policy_keys:
            missing = ", ".join(
                sorted(
                    f"{action.value}/{dimension.value}"
                    for action, dimension in missing_policy_keys
                )
            )
            raise ValueError(
                f"AUTH_ABUSE_POLICIES is missing required policies: {missing}"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
