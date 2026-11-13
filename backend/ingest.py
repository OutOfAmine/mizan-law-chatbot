"""Official PDFs -> one passage per article -> Gemini embeddings -> pgvector.

    python ingest.py --dry     # parse only, print counts (no API key needed)
    python ingest.py           # parse + embed (locally) + store, resumes
    python ingest.py --fresh   # drop the table and re-embed everything
"""
import re
import sys
import time
from pathlib import Path

from pypdf import PdfReader

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

DOCS = [
    {
        "file": "code_travail.pdf",
        "source": "Code du travail",
        "url": "https://adala.justice.gov.ma/api/uploads/2024/04/30/code%20du%20travail-1714463246806.pdf",
    },
    {
        "file": "code_famille.pdf",
        "source": "Code de la famille",
        "url": "https://adala.justice.gov.ma/api/uploads/2024/12/12/DAHIR%20N%C2%B0%201-04-22%20PORTANT%20PROMULGATION%20DE%20LA%20LOI.PDF-1734012188728.pdf",
    },
    {
        "file": "constitution.pdf",
        "source": "Constitution",
        "url": "https://adala.justice.gov.ma/api/uploads/2024/02/28/costitution-1709118294788.pdf",
    },
]

HEAD = re.compile(r"^\s*Article\s+(premier|1\s?er|\d+(?:-\d+)?(?:\s?bis)?)\s*\.?\s*[-–:]?\s*$", re.I | re.M)
PAGE_NO = re.compile(r"^\s*-\s*\d+\s*-\s*$", re.M)
MAX = 2400  # chars per passage; long articles get split in parts

# Section headings, e.g. "CHAPITRE III: DE LA GARDE" (+ its continuation line if it
# is not an article). Each article gets its heading path as context.
LEVELS = ["livre", "titre", "chapitre", "section"]
TITLE = re.compile(
    r"^\s*(livre|titre|chapitre|section)\b[^\n]{0,90}(?:\n(?!\s*(?:article|livre|titre|chapitre|section)\b)[^\n]{1,90})?",
    re.I | re.M,
)


def parse(doc: dict) -> list[dict]:
    reader = PdfReader(RAW / doc["file"])
    # keep page numbers so each source link can open at the right page
    marked = []
    for i, p in enumerate(reader.pages, start=1):
        t = PAGE_NO.sub("", p.extract_text() or "")
        marked.append(f"\n<<P{i}>>\n{t}")
    text = "".join(marked)

    heads = list(HEAD.finditer(text))
    titles = list(TITLE.finditer(text))
    out, seen = [], set()
    crumb: dict[str, str] = {}
    ti = 0
    for h, nxt in zip(heads, heads[1:] + [None]):
        # update the Livre > Titre > Chapitre > Section path seen before this article
        while ti < len(titles) and titles[ti].start() < h.start():
            m = titles[ti]
            level = LEVELS.index(m.group(1).lower())
            name = re.sub(r"\s+", " ", (m.group(0)).replace("\n", " ")).strip()
            name = re.sub(r"<<P\d+>>", "", name).strip()
            for lv in LEVELS[level:]:
                crumb.pop(lv, None)
            crumb[LEVELS[level]] = name
            ti += 1
        path_txt = " > ".join(crumb[lv] for lv in LEVELS if lv in crumb)

        num = h.group(1).lower().replace(" ", "")
        num = "1" if num in ("premier", "1er") else num
        end = nxt.start() if nxt else len(text)
        # a heading between two articles belongs to the next one, not to this body
        nt = next((t for t in titles[ti:] if t.start() < end), None)
        body = text[h.end(): nt.start() if nt else end]
        pages = re.findall(r"<<P(\d+)>>", text[: h.start()])
        page = int(pages[-1]) if pages else 1
        body = re.sub(r"<<P\d+>>", " ", body)
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n\s*\n+", "\n", body).strip()
        if len(body) < 20:
            continue
        ref = f"Article {num}"
        if (ref) in seen:  # same number again = annex/other law inside the PDF
            continue
        seen.add(ref)
        parts = [body[i: i + MAX] for i in range(0, len(body), MAX)]
        for k, part in enumerate(parts):
            out.append({
                "source": doc["source"],
                "article": ref if len(parts) == 1 else f"{ref} ({k + 1}/{len(parts)})",
                "text": f"{doc['source']} — {ref}\n[{path_txt}]\n{part}" if path_txt else f"{doc['source']} — {ref}\n{part}",
                "url": f"{doc['url']}#page={page}",
            })
    return out


def main(dry: bool) -> None:
    rows = [r for d in DOCS for r in parse(d)]
    for d in DOCS:
        n = sum(r["source"] == d["source"] for r in rows)
        print(f"{d['source']}: {n} passages")
    if dry:
        demo = next(r for r in rows if r["source"] == "Code du travail" and r["article"] == "Article 231")
        print("\n--- sample ---\n", demo["text"][:400], "\n", demo["url"])
        return

    from app.db import connect, init_schema
    from app.embedder import embed_passages

    conn = connect()
    if "--fresh" in sys.argv:
        conn.execute("DROP TABLE IF EXISTS chunks")
    init_schema(conn)
    have = {(s, a) for s, a in conn.execute("SELECT source, article FROM chunks").fetchall()}
    rows = [r for r in rows if (r["source"], r["article"]) not in have]
    print(f"to embed: {len(rows)} (already stored: {len(have)})")
    B = 64
    t0 = time.time()
    for i in range(0, len(rows), B):
        batch = rows[i: i + B]
        vecs = embed_passages([r["text"] for r in batch])
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (source, article, text, url, embedding)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (source, article) DO UPDATE
                   SET text = EXCLUDED.text, url = EXCLUDED.url, embedding = EXCLUDED.embedding""",
                [(r["source"], r["article"], r["text"], r["url"], v) for r, v in zip(batch, vecs)],
            )
        print(f"  stored {min(i + B, len(rows))}/{len(rows)}  ({time.time() - t0:.0f}s)")
    print("done")


if __name__ == "__main__":
    main("--dry" in sys.argv)
