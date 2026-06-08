from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


_password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(
        plain_password: str,
        hashed_password: str,
) -> bool:
    try:
        return _password_hasher.verify(
            plain_password,
            hashed_password,
        )
    except UnknownHashError:
        return False