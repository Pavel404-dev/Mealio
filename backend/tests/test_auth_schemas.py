import pytest
from pydantic import SecretStr, ValidationError

from app.schemas.auth import UserLogin, UserRegister


VALID_PASSWORD = "Mealio-secure-15"

VALID_DATA: dict[str, object] = {
    "email": "pavel@example.com",
    "full_name": "Pavel Potapenko",
    "password": VALID_PASSWORD,
}

VALID_LOGIN_PASSWORD = "LoginPassword"

VALID_LOGIN_DATA: dict[str, object] = {
    "email": "pavel@example.com",
    "password": VALID_LOGIN_PASSWORD,
}


def build_registration_data(
    **overrides: object,
) -> dict[str, object]:
    return {
        **VALID_DATA,
        **overrides,
    }


def build_login_data(
    **overrides: object,
) -> dict[str, object]:
    return {
        **VALID_LOGIN_DATA,
        **overrides,
    }


def test_valid_registration_data_creates_schema() -> None:
    registration = UserRegister.model_validate(VALID_DATA)

    assert str(registration.email) == "pavel@example.com"
    assert registration.full_name == "Pavel Potapenko"
    assert (
        registration.password.get_secret_value()
        == VALID_PASSWORD
    )


def test_email_is_trimmed_and_lowercased() -> None:
    registration = UserRegister.model_validate(
        build_registration_data(
            email="  Pavel.User@Example.COM  ",
        )
    )

    assert (
        str(registration.email)
        == "pavel.user@example.com"
    )


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                email="not-an-email",
            )
        )


def test_missing_email_is_rejected() -> None:
    data = build_registration_data()
    data.pop("email")

    with pytest.raises(ValidationError):
        UserRegister.model_validate(data)


def test_null_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                email=None,
            )
        )


def test_full_name_is_trimmed() -> None:
    registration = UserRegister.model_validate(
        build_registration_data(
            full_name="  Pavel Potapenko  ",
        )
    )

    assert registration.full_name == "Pavel Potapenko"


def test_empty_full_name_is_normalized_to_none() -> None:
    registration = UserRegister.model_validate(
        build_registration_data(
            full_name="",
        )
    )

    assert registration.full_name is None


def test_whitespace_only_full_name_is_normalized_to_none() -> None:
    registration = UserRegister.model_validate(
        build_registration_data(
            full_name="   ",
        )
    )

    assert registration.full_name is None


def test_null_full_name_is_allowed() -> None:
    registration = UserRegister.model_validate(
        build_registration_data(
            full_name=None,
        )
    )

    assert registration.full_name is None


def test_full_name_longer_than_255_characters_is_rejected(
) -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                full_name="a" * 256,
            )
        )


def test_password_with_exact_minimum_length_is_allowed(
) -> None:
    password = "a" * 15

    registration = UserRegister.model_validate(
        build_registration_data(
            password=password,
        )
    )

    assert (
        registration.password.get_secret_value()
        == password
    )


def test_password_shorter_than_minimum_length_is_rejected(
) -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                password="a" * 14,
            )
        )


def test_password_longer_than_maximum_length_is_rejected(
) -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                password="a" * 129,
            )
        )


def test_missing_password_is_rejected() -> None:
    data = build_registration_data()
    data.pop("password")

    with pytest.raises(ValidationError):
        UserRegister.model_validate(data)


def test_null_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                password=None,
            )
        )


def test_whitespace_only_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            build_registration_data(
                password=" " * 15,
            )
        )


def test_unicode_password_is_allowed() -> None:
    password = "Mealio-Пароль-🔐"

    registration = UserRegister.model_validate(
        build_registration_data(
            password=password,
        )
    )

    assert (
        registration.password.get_secret_value()
        == password
    )


def test_password_leading_and_trailing_spaces_are_preserved(
) -> None:
    password = "  Mealio-password  "

    registration = UserRegister.model_validate(
        build_registration_data(
            password=password,
        )
    )

    assert (
        registration.password.get_secret_value()
        == password
    )


def test_password_is_not_lowercased() -> None:
    password = "MealioPasswordABC"

    registration = UserRegister.model_validate(
        build_registration_data(
            password=password,
        )
    )

    assert (
        registration.password.get_secret_value()
        == password
    )


def test_password_is_masked_in_schema_representation(
) -> None:
    registration = UserRegister.model_validate(
        VALID_DATA
    )

    assert VALID_PASSWORD not in repr(registration)
    assert VALID_PASSWORD not in str(registration)
    assert (
        VALID_PASSWORD
        not in registration.model_dump_json()
    )
    assert "**********" in repr(registration)


def test_validation_error_string_does_not_expose_password(
) -> None:
    invalid_password = "too-short"

    with pytest.raises(ValidationError) as exc_info:
        UserRegister.model_validate(
            build_registration_data(
                password=invalid_password,
            )
        )

    assert invalid_password not in str(exc_info.value)


def test_valid_login_data_creates_schema() -> None:
    login = UserLogin.model_validate(VALID_LOGIN_DATA)

    assert str(login.email) == "pavel@example.com"
    assert (
        login.password.get_secret_value()
        == VALID_LOGIN_PASSWORD
    )


def test_login_email_is_trimmed_and_lowercased() -> None:
    login = UserLogin.model_validate(
        build_login_data(
            email="  Pavel.User@Example.COM  ",
        )
    )

    assert str(login.email) == "pavel.user@example.com"


def test_login_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserLogin.model_validate(
            build_login_data(
                email="not-an-email",
            )
        )


def test_login_missing_email_is_rejected() -> None:
    data = build_login_data()
    data.pop("email")

    with pytest.raises(ValidationError):
        UserLogin.model_validate(data)


def test_login_null_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserLogin.model_validate(
            build_login_data(
                email=None,
            )
        )


def test_login_password_uses_secret_str() -> None:
    login = UserLogin.model_validate(VALID_LOGIN_DATA)

    assert isinstance(login.password, SecretStr)


def test_login_missing_password_is_rejected() -> None:
    data = build_login_data()
    data.pop("password")

    with pytest.raises(ValidationError):
        UserLogin.model_validate(data)


def test_login_null_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserLogin.model_validate(
            build_login_data(
                password=None,
            )
        )


def test_login_empty_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserLogin.model_validate(
            build_login_data(
                password="",
            )
        )


def test_login_password_longer_than_128_characters_is_rejected(
) -> None:
    with pytest.raises(ValidationError):
        UserLogin.model_validate(
            build_login_data(
                password="a" * 129,
            )
        )


def test_login_password_shorter_than_registration_minimum_is_allowed(
) -> None:
    password = "short"

    login = UserLogin.model_validate(
        build_login_data(
            password=password,
        )
    )

    assert login.password.get_secret_value() == password


def test_login_unicode_password_is_allowed() -> None:
    password = "Пароль-🔐"

    login = UserLogin.model_validate(
        build_login_data(
            password=password,
        )
    )

    assert login.password.get_secret_value() == password


def test_login_password_case_is_preserved() -> None:
    password = "LoginPasswordABC"

    login = UserLogin.model_validate(
        build_login_data(
            password=password,
        )
    )

    assert login.password.get_secret_value() == password


def test_login_password_surrounding_spaces_are_preserved(
) -> None:
    password = "  LoginPassword  "

    login = UserLogin.model_validate(
        build_login_data(
            password=password,
        )
    )

    assert login.password.get_secret_value() == password


def test_login_password_is_masked_in_schema_representation(
) -> None:
    login = UserLogin.model_validate(VALID_LOGIN_DATA)

    assert VALID_LOGIN_PASSWORD not in repr(login)
    assert VALID_LOGIN_PASSWORD not in str(login)
    assert (
        VALID_LOGIN_PASSWORD
        not in login.model_dump_json()
    )
    assert "**********" in repr(login)


def test_login_validation_error_does_not_expose_password(
) -> None:
    invalid_password = "VisibleSecret-" + ("x" * 120)

    with pytest.raises(ValidationError) as exc_info:
        UserLogin.model_validate(
            build_login_data(
                password=invalid_password,
            )
        )

    assert invalid_password not in str(exc_info.value)


def test_login_whitespace_only_password_is_allowed_and_preserved(
) -> None:
    password = "   "

    login = UserLogin.model_validate(
        build_login_data(
            password=password,
        )
    )

    assert login.password.get_secret_value() == password
