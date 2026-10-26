"""Fail-closed destructive-test targets: legacy CI or an attested isolated run.

The external attestation is produced by the container owner, never by fixtures.
It binds the URL to a Docker ID, run label, pinned image and fresh cluster ID.
"""

import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

IMAGES = {
    17: "sha256:2203e6282d9e7de7c24d7da234e2a744fb325df366a3fd8ed940e8abbee39527",
    18: "sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280",
}
IDENTITY_SQL = """SELECT current_database(), session_user,
current_setting('server_encoding'), current_setting('server_version_num')::int / 10000,
(SELECT system_identifier::text FROM pg_control_system())"""


def target_url():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    assert url.drivername == "postgresql+asyncpg", "Unexpected test driver"
    path = os.environ.get("MEALIO_TEST_TARGET")
    if not path:
        assert (url.host, url.port, url.database, url.username) == (
            "localhost",
            5432,
            "mealio_test",
            "mealio_user",
        ), "Only the established CI target is allowed without an attestation"
        return url, None
    record = json.loads(Path(path).read_text())
    assert record["major"] in IMAGES
    assert record["image_id"] == IMAGES[record["major"]]
    assert record["name"] == f"mealio-205-integration-pg{record['major']}"
    assert record["database"] == "mealio_205_test"
    assert record["port"] != 5432
    assert (url.host, url.port, url.database, url.username) == (
        "127.0.0.1",
        record["port"],
        record["database"],
        record["user"],
    ), "Test URL does not match the authorized endpoint"
    assert len(record["container_id"]) == 64 and record["run_label"]
    return url, record


def verify_docker_target():
    url, record = target_url()
    if record is None:
        return url
    result = subprocess.run(
        [
            "docker",
            "inspect",
            record["container_id"],
            "--format",
            '{"id":{{json .Id}},"image":{{json .Image}},'
            '"labels":{{json .Config.Labels}},"ports":{{json .NetworkSettings.Ports}},'
            '"running":{{json .State.Running}},"mounts":{{json .Mounts}}}',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    actual = json.loads(result.stdout)
    assert actual["id"] == record["container_id"] and actual["running"]
    assert actual["image"] == record["image_id"]
    assert actual["labels"]["mealio205.run"] == record["run_label"]
    assert actual["ports"] == {
        "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(record["port"])}]
    }
    assert not any(m["Type"] in ("bind", "volume") for m in actual["mounts"])
    return url


def assert_identity(row):
    url, record = target_url()
    assert row[0] == url.database and row[1] == url.username
    assert row[2] == "UTF8"
    if record:
        assert row[3] == record["major"] and row[4] == record["system_identifier"]


async def verify_connection(connection):
    verify_docker_target()
    assert_identity((await connection.execute(text(IDENTITY_SQL))).one())


async def verify_asyncpg(connection):
    verify_docker_target()
    assert_identity(await connection.fetchrow(IDENTITY_SQL))


def before_connect(dialect, connection_record, args, params):
    """Reject wrong endpoints before SQLAlchemy/Alembic opens a connection."""
    url, _ = target_url()
    assert (
        params.get("host"),
        params.get("port"),
        params.get("database"),
        params.get("user"),
    ) == (
        url.host,
        url.port,
        url.database,
        url.username,
    ), "Connection outside the authorized test endpoint"


def after_connect(connection, connection_record):
    cursor = connection.cursor()
    try:
        cursor.execute(IDENTITY_SQL)
        assert_identity(cursor.fetchone())
        cursor.execute("SET statement_timeout = '60s'")
        cursor.execute("SET lock_timeout = '10s'")
    finally:
        cursor.close()
