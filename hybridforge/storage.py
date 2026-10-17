"""Transactional stores. SQLite is a bounded demo; PostgreSQL is the deployment adapter."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from .models import Conflict, Hit
from .retrieval import bm25, cosine


class SQLiteStore:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                  tenant TEXT, document_id TEXT, version INTEGER, digest TEXT,
                  title TEXT, source TEXT, acl TEXT, embedding_id TEXT,
                  PRIMARY KEY (tenant, document_id));
                CREATE TABLE IF NOT EXISTS chunks (
                  tenant TEXT, document_id TEXT, chunk_id TEXT, hit TEXT, embedding TEXT,
                  PRIMARY KEY (tenant, chunk_id),
                  FOREIGN KEY (tenant, document_id) REFERENCES documents ON DELETE CASCADE);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def ready(self):
        with self.connection() as db:
            db.execute("SELECT 1").fetchone()

    def close(self):
        pass

    def upsert(self, p, doc, digest, chunks, vectors, embedding_id):
        if not p.can_write:
            raise PermissionError("Writer scope required")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM documents WHERE tenant=? AND document_id=?",
                (p.tenant, doc.document_id),
            ).fetchone()
            if old and old["digest"] == digest:
                return {"document_id": doc.document_id, "version": old["version"], "changed": False}
            if (old["version"] if old else 0) != doc.expected_version:
                raise Conflict("Document version changed; refresh before replacing")
            version = doc.expected_version + 1
            db.execute(
                "DELETE FROM documents WHERE tenant=? AND document_id=?",
                (p.tenant, doc.document_id),
            )
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                (
                    p.tenant,
                    doc.document_id,
                    version,
                    digest,
                    doc.title,
                    doc.source,
                    json.dumps(doc.acl_groups),
                    embedding_id,
                ),
            )
            for h, vector in zip(chunks, vectors, strict=True):
                db.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?)",
                    (
                        p.tenant,
                        doc.document_id,
                        h.chunk_id,
                        json.dumps(asdict(replace(h, version=version))),
                        json.dumps(vector),
                    ),
                )
            return {
                "document_id": doc.document_id,
                "version": version,
                "changed": True,
                "chunks": len(chunks),
            }

    @staticmethod
    def visible(p, row):
        groups = json.loads(row["acl"])
        return p.can_write or not groups or bool(set(p.groups).intersection(groups))

    def search(self, p, question, vector, embedding_id, limit, minimum):
        with self.connection() as db:
            rows = db.execute(
                """SELECT c.hit,c.embedding,d.acl FROM chunks c JOIN documents d
                ON c.tenant=d.tenant AND c.document_id=d.document_id
                WHERE c.tenant=? AND d.embedding_id=?""",
                (p.tenant, embedding_id),
            ).fetchall()
        allowed = [r for r in rows if self.visible(p, r)]
        hits = [Hit(**json.loads(r["hit"])) for r in allowed]
        lexical = bm25(question, hits)[:limit]
        dense = [
            replace(h, score=cosine(vector, json.loads(r["embedding"])))
            for h, r in zip(hits, allowed)
        ]
        dense = sorted(
            [h for h in dense if h.score >= minimum], key=lambda h: (-h.score, h.chunk_id)
        )[:limit]
        return lexical, dense

    def list_documents(self, p):
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM documents WHERE tenant=? ORDER BY document_id", (p.tenant,)
            ).fetchall()
        return [
            {k: r[k] for k in ["document_id", "version", "title", "source", "embedding_id"]}
            for r in rows
            if self.visible(p, r)
        ]

    def delete(self, p, document_id, version):
        if not p.can_write:
            raise PermissionError("Writer scope required")
        with self.connection() as db:
            result = db.execute(
                "DELETE FROM documents WHERE tenant=? AND document_id=? AND version=?",
                (p.tenant, document_id, version),
            )
            if not result.rowcount:
                raise Conflict("Document not found or version changed")


class PostgresStore:
    def __init__(self, url):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            url, min_size=1, max_size=12, timeout=5, kwargs={"row_factory": dict_row}, open=True
        )
        self.pool.wait(timeout=10)
        self.ready()

    def close(self):
        self.pool.close()

    def ready(self):
        with self.pool.connection() as db:
            role = db.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if role["rolsuper"] or role["rolbypassrls"]:
                raise RuntimeError("Application database role must not bypass RLS")
            version = db.execute("SELECT version FROM schema_version WHERE version=1").fetchone()
            tables = db.execute("""SELECT relname,relrowsecurity,relforcerowsecurity
                FROM pg_class WHERE oid IN ('documents'::regclass,'chunks'::regclass)""").fetchall()
            if (
                not version
                or len(tables) != 2
                or not all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in tables)
            ):
                raise RuntimeError("Database migration or RLS configuration missing")

    @contextmanager
    def transaction(self, p, snapshot=False):
        with self.pool.connection() as db:
            with db.transaction():
                if snapshot:
                    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                for key, value in [
                    ("app.tenant", p.tenant),
                    ("app.groups", json.dumps(p.groups)),
                    ("app.can_write", str(p.can_write).lower()),
                    ("statement_timeout", "5000"),
                    ("lock_timeout", "2000"),
                ]:
                    db.execute("SELECT set_config(%s,%s,true)", (key, value))
                yield db

    def upsert(self, p, doc, digest, chunks, vectors, embedding_id):
        if not p.can_write:
            raise PermissionError("Writer scope required")
        with self.transaction(p) as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (p.tenant + ":" + doc.document_id,),
            )
            old = db.execute(
                "SELECT version,digest FROM documents WHERE tenant=%s AND document_id=%s",
                (p.tenant, doc.document_id),
            ).fetchone()
            if old and old["digest"] == digest:
                return {"document_id": doc.document_id, "version": old["version"], "changed": False}
            if (old["version"] if old else 0) != doc.expected_version:
                raise Conflict("Document version changed; refresh before replacing")
            version = doc.expected_version + 1
            db.execute(
                "DELETE FROM documents WHERE tenant=%s AND document_id=%s",
                (p.tenant, doc.document_id),
            )
            db.execute(
                """INSERT INTO documents
                (tenant,document_id,version,digest,title,source,acl_groups,embedding_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    p.tenant,
                    doc.document_id,
                    version,
                    digest,
                    doc.title,
                    doc.source,
                    doc.acl_groups,
                    embedding_id,
                ),
            )
            with db.cursor() as cur:
                cur.executemany(
                    """INSERT INTO chunks
                    (tenant,document_id,chunk_id,version,title,source,body,start_char,end_char,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                    [
                        (
                            p.tenant,
                            h.document_id,
                            h.chunk_id,
                            version,
                            h.title,
                            h.source,
                            h.text,
                            h.start,
                            h.end,
                            json.dumps(v),
                        )
                        for h, v in zip(chunks, vectors, strict=True)
                    ],
                )
            return {
                "document_id": doc.document_id,
                "version": version,
                "changed": True,
                "chunks": len(chunks),
            }

    @staticmethod
    def hit(row):
        return Hit(
            row["chunk_id"],
            row["document_id"],
            row["version"],
            row["title"],
            row["source"],
            row["body"],
            row["start_char"],
            row["end_char"],
            float(row["score"]),
        )

    def search(self, p, question, vector, embedding_id, limit, minimum):
        with self.transaction(p, snapshot=True) as db:
            lexical = db.execute(
                """SELECT c.*,ts_rank_cd(c.search_vector,q) AS score
                FROM chunks c JOIN documents d USING (tenant,document_id),
                websearch_to_tsquery('english',%s) q
                WHERE c.tenant=%s AND d.embedding_id=%s AND c.search_vector @@ q
                ORDER BY score DESC,c.chunk_id LIMIT %s""",
                (question, p.tenant, embedding_id, limit),
            ).fetchall()
            # Materialize the authorized subset; exact search is deliberate for v1.
            # Adding a global ANN index alone will not change this execution plan.
            dense = db.execute(
                """WITH authorized AS MATERIALIZED (
                SELECT c.* FROM chunks c JOIN documents d USING (tenant,document_id)
                WHERE c.tenant=%s AND d.embedding_id=%s)
                SELECT *,1-(embedding <=> %s::vector) AS score FROM authorized
                WHERE 1-(embedding <=> %s::vector) >= %s
                ORDER BY score DESC,chunk_id LIMIT %s""",
                (p.tenant, embedding_id, json.dumps(vector), json.dumps(vector), minimum, limit),
            ).fetchall()
        return [self.hit(r) for r in lexical], [self.hit(r) for r in dense]

    def list_documents(self, p):
        with self.transaction(p) as db:
            return db.execute(
                """SELECT document_id,version,title,source,embedding_id
                FROM documents WHERE tenant=%s ORDER BY document_id LIMIT 1000""",
                (p.tenant,),
            ).fetchall()

    def delete(self, p, document_id, version):
        if not p.can_write:
            raise PermissionError("Writer scope required")
        with self.transaction(p) as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (p.tenant + ":" + document_id,),
            )
            result = db.execute(
                "DELETE FROM documents WHERE tenant=%s AND document_id=%s AND version=%s",
                (p.tenant, document_id, version),
            )
            if not result.rowcount:
                raise Conflict("Document not found or version changed")
