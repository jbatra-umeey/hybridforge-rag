"""One-shot v1 migration. Supply an owner DSN and a separate application password."""

import os
from pathlib import Path

import psycopg
from psycopg import sql

dsn = os.environ["MIGRATION_DATABASE_URL"]
password = os.environ["RAG_DB_PASSWORD"]
if len(password) < 20:
    raise SystemExit("RAG_DB_PASSWORD must contain at least 20 characters")
with psycopg.connect(dsn, autocommit=True) as db:
    # Session advisory lock serializes concurrent migration jobs.
    db.execute("SELECT pg_advisory_lock(84910001)")
    try:
        if not db.execute("SELECT to_regclass('public.schema_version')").fetchone()[0]:
            db.execute(
                (Path(__file__).resolve().parents[1] / "migrations/001_init.sql").read_text()
            )
        versions = db.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        if versions != [(1,)]:
            raise RuntimeError("Unexpected database version; review migrations")
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='rag_app'").fetchone():
            db.execute(
                sql.SQL(
                    "CREATE ROLE rag_app LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
                ).format(sql.Literal(password))
            )
        # Existing passwords are deliberately not silently rotated by migration.
        db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        db.execute("GRANT USAGE ON SCHEMA public TO rag_app")
        db.execute("GRANT SELECT ON schema_version TO rag_app")
        db.execute("GRANT SELECT,INSERT,DELETE ON documents,chunks TO rag_app")
        print("Schema v1 is installed; application grants applied")
    finally:
        db.execute("SELECT pg_advisory_unlock(84910001)")
