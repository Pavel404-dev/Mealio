from sqlalchemy import CheckConstraint, Enum as SqlEnum

from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose


def test_email_otp_purposes_are_explicit_and_limited() -> None:
    assert [purpose.value for purpose in EmailOtpPurpose] == [
        "email_verification",
        "password_reset",
    ]


def test_email_otp_challenge_has_expected_columns() -> None:
    assert set(EmailOtpChallenge.__table__.columns.keys()) == {
        "id",
        "user_id",
        "purpose",
        "target_email",
        "code_digest",
        "expires_at",
        "failed_attempts",
        "send_count",
        "last_sent_at",
        "used_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }


def test_email_otp_challenge_never_has_raw_code_column() -> None:
    column_names = set(EmailOtpChallenge.__table__.columns.keys())

    assert {"code", "otp", "otp_code", "raw_code"}.isdisjoint(column_names)
    assert "code_digest" in column_names


def test_email_otp_digest_is_not_unique() -> None:
    code_digest = EmailOtpChallenge.__table__.c.code_digest

    assert code_digest.unique is not True


def test_email_otp_purpose_uses_non_native_enum_values() -> None:
    purpose_type = EmailOtpChallenge.__table__.c.purpose.type

    assert isinstance(purpose_type, SqlEnum)
    assert purpose_type.native_enum is False
    assert purpose_type.enums == ["email_verification", "password_reset"]


def test_email_otp_challenge_has_lifecycle_constraints() -> None:
    check_names = {
        constraint.name
        for constraint in EmailOtpChallenge.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_email_otp_challenges_failed_attempts_nonnegative" in check_names
    assert "ck_email_otp_challenges_send_count_positive" in check_names
    assert "email_otp_purpose" in check_names


def test_email_otp_challenge_has_account_purpose_lookup_index() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in EmailOtpChallenge.__table__.indexes
    }

    assert indexes["ix_email_otp_challenges_user_purpose_email_created_at"] == (
        "user_id",
        "purpose",
        "target_email",
        "created_at",
    )
    assert indexes["ix_email_otp_challenges_expires_at"] == ("expires_at",)
