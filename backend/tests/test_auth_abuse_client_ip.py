import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.deps import get_direct_client_ip


def _request(
    *,
    client: tuple[str, int] | None,
    forwarded_for: str | None = None,
) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))

    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": headers,
            "client": client,
            "server": ("testserver", 80),
        }
    )


def test_direct_client_ip_ignores_forwarded_headers() -> None:
    request = _request(
        client=("203.0.113.10", 12345),
        forwarded_for="198.51.100.20",
    )

    assert get_direct_client_ip(request) == "203.0.113.10"


def test_direct_client_ip_normalizes_ipv6() -> None:
    request = _request(
        client=("2001:0db8:0000:0000:0000:0000:0000:0001", 12345),
    )

    assert get_direct_client_ip(request) == "2001:db8::1"


@pytest.mark.parametrize(
    "client",
    [
        None,
        ("not-an-ip", 12345),
    ],
)
def test_direct_client_ip_fails_closed_when_peer_is_unavailable(
    client: tuple[str, int] | None,
) -> None:
    request = _request(client=client)

    with pytest.raises(HTTPException) as exc_info:
        get_direct_client_ip(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Authentication protection is unavailable"
