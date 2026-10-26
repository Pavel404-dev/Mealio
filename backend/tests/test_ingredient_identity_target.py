"""Target-guard regressions do not open any connection."""

import pytest

from tests.db_target import before_connect, target_url


@pytest.mark.parametrize(
    "endpoint",
    [
        "localhost:5432/mealio_205_test",
        "127.0.0.1:5432/mealio_test",
        "localhost:5432/mealio",
        "localhost:5433/mealio_test",
    ],
)
def test_unattested_alternate_targets_fail_closed(monkeypatch, endpoint):
    monkeypatch.delenv("MEALIO_TEST_TARGET", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL", f"postgresql+asyncpg://mealio_user:synthetic@{endpoint}"
    )
    with pytest.raises(AssertionError):
        target_url()


def test_existing_ci_target_and_preconnect_endpoint_guard(monkeypatch):
    monkeypatch.delenv("MEALIO_TEST_TARGET", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://mealio_user:synthetic@localhost:5432/mealio_test",
    )
    url, attestation = target_url()
    assert url.database == "mealio_test" and attestation is None
    with pytest.raises(AssertionError, match="outside the authorized"):
        before_connect(
            None,
            None,
            (),
            {
                "host": "elsewhere",
                "port": 5432,
                "database": "mealio_test",
                "user": "mealio_user",
            },
        )
