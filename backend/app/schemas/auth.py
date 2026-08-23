from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128


def _normalize_email(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()

    return value


def _validate_new_password(value: SecretStr) -> SecretStr:
    if not value.get_secret_value().strip():
        raise ValueError("Password cannot contain only whitespace")

    return value


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str | None = Field(
        default=None,
        max_length=255,
    )
    password: SecretStr = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized_value = value.strip()
            return normalized_value or None

        return value

    @field_validator("password")
    @classmethod
    def reject_whitespace_only_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        return _validate_new_password(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr = Field(
        min_length=1,
        max_length=PASSWORD_MAX_LENGTH,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class RefreshTokenRequest(BaseModel):
    refresh_token: SecretStr = Field(
        min_length=1,
        max_length=512,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )


class EmailVerificationRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class EmailVerificationOtpRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class EmailVerificationOtpConfirm(BaseModel):
    email: EmailStr
    code: SecretStr = Field(
        json_schema_extra={
            "minLength": 6,
            "maxLength": 6,
            "pattern": "^[0-9]{6}$",
        },
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        code = value.get_secret_value()
        if not (len(code) == 6 and code.isascii() and code.isdigit()):
            raise ValueError(
                "Email verification code must contain exactly 6 ASCII digits"
            )

        return value


class EmailVerificationConfirm(BaseModel):
    token: SecretStr = Field(
        min_length=1,
        max_length=512,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )


class EmailVerificationRequestResponse(BaseModel):
    message: str


class PasswordResetRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class PasswordResetConfirm(BaseModel):
    token: SecretStr = Field(
        min_length=1,
        max_length=512,
    )
    new_password: SecretStr = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("new_password")
    @classmethod
    def reject_whitespace_only_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        return _validate_new_password(value)


class PasswordResetRequestResponse(BaseModel):
    message: str


class AccessTokenResponse(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"


class TokenPairResponse(AccessTokenResponse):
    refresh_token: str = Field(min_length=1)
