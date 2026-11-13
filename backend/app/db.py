"""Postgres + pgvector. Local dev uses pgserver (embedded Postgres, no install)."""
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from .config import settings

_uri: str | None = None


def uri() -> str:
    global _uri
    if _uri:
        return _uri
    if settings.database_url:
        _uri = settings.database_url
    else:
        import pgserver

        data = Path(__file__).resolve().parent.parent / "pgdata"
        _uri = pgserver.get_server(str(data), cleanup_mode=None).get_uri()
    return _uri


def connect() -> psycopg.Connection:
    conn = psycopg.connect(uri(), autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id          serial PRIMARY KEY,
            source      text NOT NULL,      -- e.g. "Code du travail"
            article     text NOT NULL,      -- e.g. "Article 231"
            text        text NOT NULL,
            url         text NOT NULL,      -- official document link
            embedding   vector({settings.embed_dim}) NOT NULL,
            UNIQUE (source, article)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
        "ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    # keyword side of the hybrid search (French stemming: "congés" == "congé")
    conn.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('french', text)) STORED"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv)")
