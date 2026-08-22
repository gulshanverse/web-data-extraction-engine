import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("WDE_TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("APP_ENV", "development")


@pytest.fixture(autouse=True)
def isolated_database() -> None:
    if not TEST_DATABASE_URL:
        yield
        return
    sync_url = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    with psycopg.connect(sync_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE TABLE work_outbox, idempotency_keys, progress_events, browser_artifacts, generated_files, export_jobs, validation_results, records, pages, extraction_plans, extraction_jobs, sources, projects, users RESTART IDENTITY CASCADE"
            )
            cursor.execute(
                "INSERT INTO users (id, email, status) VALUES ('11111111-1111-1111-1111-111111111111', 'developer@example.invalid', 'ACTIVE')"
            )
            cursor.execute(
                "INSERT INTO projects (id, owner_id, name, status) VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'Phase 2 Test Project', 'ACTIVE')"
            )
        connection.commit()
    yield
