"""Display trimming/storage validation only. SQL defines name equivalence."""

from app.db.ddl.ingredient_identity_v1 import WHITESPACE


def validate_storage_text(value: str) -> str:
    if any(c == "\x00" or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("Text contains characters unsupported by PostgreSQL UTF8")
    return value


def trim_ingredient_name(value):
    if isinstance(value, str):
        return validate_storage_text(value).strip(WHITESPACE)
    return value
