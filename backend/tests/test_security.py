from app.core.security import hash_password, verify_password


def test_hash_password_does_not_return_plaintext() -> None:
    plain_password = "Mealio-secure-password"

    hashed_password = hash_password(plain_password)

    assert hashed_password != plain_password


def test_hash_password_uses_argon2_format() -> None:
    hashed_password = hash_password("Mealio-secure-password")

    assert hashed_password.startswith("$argon2id$")
    assert len(hashed_password) <= 255


def test_verify_password_accepts_correct_password() -> None:
    plain_password = "Mealio-secure-password"
    hashed_password = hash_password(plain_password)

    assert verify_password(plain_password, hashed_password) is True


def test_verify_password_rejects_incorrect_password() -> None:
    hashed_password = hash_password("correct-password")

    assert verify_password(
        "incorrect-password",
        hashed_password,
    ) is False


def test_hash_password_uses_random_salt() -> None:
    plain_password = "Mealio-secure-password"

    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert first_hash != second_hash


def test_both_hashes_verify_for_same_password() -> None:
    plain_password = "Mealio-secure-password"

    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert verify_password(plain_password, first_hash) is True
    assert verify_password(plain_password, second_hash) is True


def test_verify_password_rejects_invalid_or_unknown_hash() -> None:
    plain_password = "Mealio-secure-password"

    assert verify_password(
        plain_password,
        "not-a-valid-password-hash",
    ) is False

    assert verify_password(
        plain_password,
        "$argon2id$v=19$m=65536,t=3,p=4$invalid",
    ) is False


def test_unicode_password_can_be_hashed_and_verified() -> None:
    plain_password = "Mealio-Пароль-🔐"

    hashed_password = hash_password(plain_password)

    assert verify_password(plain_password, hashed_password) is True


def test_unicode_password_rejects_different_value() -> None:
    plain_password = "Mealio-Пароль-🔐"
    different_password = "Mealio-Пароль-🔓"

    hashed_password = hash_password(plain_password)

    assert verify_password(
        different_password,
        hashed_password,
    ) is False

def test_verify_password_rejects_missing_hash() -> None:
    assert verify_password("Mealio-secure-password", None) is False
    assert verify_password("Mealio-secure-password", "") is False