"""Hybrid retrieval: meaning (pgvector) + exact legal words (Postgres full-text),
merged with Reciprocal Rank Fusion. Darija questions are first rewritten into
French legal terms so both searches can match the official text."""
from .config import settings
from .db import connect, init_schema
from .embedder import aembed_queries, arerank
from .llm import rewrite_query

_conn = None
K = 20      # candidates per search before fusion
RRF = 60    # standard RRF constant


def conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
        init_schema(_conn)
    return _conn


def _vector(vec: list[float]) -> list[tuple]:
    return conn().execute(
        """SELECT source, article, text, url, 1 - (embedding <=> %s::vector) AS sim
           FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s""",
        (vec, vec, K),
    ).fetchall()


def _keywords(q: str) -> list[tuple]:
    """Articles containing ALL the legal words first, then ANY of them."""
    sql = """SELECT source, article, text, url, ts_rank_cd(tsv, t, 32) AS r
             FROM chunks, (SELECT {tsq} AS t) q
             WHERE tsv @@ t ORDER BY r DESC LIMIT %s"""
    strict = conn().execute(sql.format(tsq="plainto_tsquery('french', %s)"), (q, K)).fetchall()
    if len(strict) >= 5:
        return strict
    loose = conn().execute(
        sql.format(tsq="NULLIF(replace(plainto_tsquery('french', %s)::text, '&', '|'), '')::tsquery"), (q, K)
    ).fetchall()
    seen = {(r[0], r[1]) for r in strict}
    return strict + [r for r in loose if (r[0], r[1]) not in seen][: K - len(strict)]


async def search(question: str) -> list[dict]:
    legal = await rewrite_query(question)
    queries = [question] + ([legal] if legal else [])
    vecs = await aembed_queries(queries)

    rows: dict[tuple, dict] = {}
    score: dict[tuple, float] = {}

    def add(results, vector: bool):
        for rank, (s, a, t, u, val) in enumerate(results):
            key = (s, a)
            row = rows.setdefault(key, {"source": s, "article": a, "text": t, "url": u, "sim": 0.0, "kw": False})
            if vector:
                row["sim"] = max(row["sim"], float(val))
            else:
                row["kw"] = True
            score[key] = score.get(key, 0) + 1 / (RRF + rank)

    for v in vecs:
        add(_vector(v), vector=True)
    add(_keywords(legal or question), vector=False)

    ranked = [rows[k] for k in sorted(rows, key=lambda k: -score[k])]
    if settings.use_rerank and ranked:
        # optional cross-encoder (more precise, but ~5-10 s on CPU)
        pool = ranked[: settings.rerank_pool]
        for p, sc in zip(pool, await arerank(legal or question, [p["text"][:1500] for p in pool])):
            p["score"] = sc
        ranked = sorted(pool, key=lambda p: -p["score"])
    hits = ranked[: settings.top_k]
    # keep a passage if the legal words matched OR the meaning is close;
    # Gemini then reads them all and cites only the right article(s)
    return [h for h in hits if h["kw"] or h["sim"] >= settings.min_similarity]
