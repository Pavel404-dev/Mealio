from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str | None = Field(
        default=None,
        max_length=255,
    )
    password: SecretStr = Field(
        min_length=15,
        max_length=128,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()

        return value

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
        if not value.get_secret_value().strip():
            raise ValueError("Password cannot contain only whitespace")

        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr = Field(
        min_length=1,
        max_length=128,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()

        return value


class RefreshTokenRequest(BaseModel):
    refresh_token: SecretStr = Field(
        min_length=1,
        max_length=512,
    )

    model_config = ConfigDict(
        hide_input_in_errors=True,
    )


class AccessTokenResponse(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"


class TokenPairResponse(AccessTokenResponse):
    refresh_token: str = Field(min_length=1)
