import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import guard, rag
from .config import settings
from .embedder import warm_up
from .llm import RESTART, stream_answer
from .prompts import CANARY, SYSTEM, build_prompt

@asynccontextmanager
async def lifespan(_: FastAPI):
    # load the local embedding model once at startup, not on the first question
    await asyncio.to_thread(warm_up)
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Mizan — chatbot l9anoun l meghribi", docs_url=None, redoc_url=None, lifespan=lifespan)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RateLimitExceeded)
async def too_many(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        {"error": "rate_limited", "message": "أسئلة كثيرة في وقت قصير، انتظر قليلاً."},
        status_code=429,
    )


class Ask(BaseModel):
    question: str = Field(max_length=2000)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def excerpt(text: str) -> str:
    """Article body only: drop the "Source — Article" line and the [Livre > ...] path."""
    lines = text.split(chr(10))[1:]
    if lines and lines[0].startswith("["):
        lines = lines[1:]
    return " ".join(l.strip() for l in lines)[:280]


# Arabizi as Moroccans type it: no transliteration diacritics
_ARABIZI = str.maketrans({
    "ḫ": "5", "ẖ": "5", "ḥ": "7", "Ḥ": "7", "ṭ": "t", "Ṭ": "T", "ḍ": "d", "Ḍ": "D", "ṣ": "s", "Ṣ": "S",
    "ẓ": "z", "ġ": "gh", "ʿ": "3", "ʾ": "2", "ā": "a", "ī": "i", "ū": "ou", "ë": "e", "ē": "e",
})


def darija(text: str) -> str:
    return text.translate(_ARABIZI)


BUSY = "الخدمة مشغولة حالياً، حاول مرة أخرى بعد قليل."
log = logging.getLogger("mizan")

NO_SOURCE = "لم أجد هذه المعلومة في النصوص التي لدي. يمكنك استشارة محامٍ أو الإدارة المعنية."


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
@limiter.limit(settings.rate_limit)
@limiter.limit(settings.daily_limit)
async def chat(request: Request, body: Ask):
    q = guard.clean(body.question)
    ok, reason = guard.check(q)

    async def events():
        # Each event drives the mascot: thinking -> talking -> happy / sad
        if not ok:
            yield sse("state", "refuse")
            msg = guard.REFUSAL if reason == "injection" else "اكتب سؤالاً قصيراً وواضحاً من فضلك."
            yield sse("token", msg)
            yield sse("done", {"blocked": reason})
            return

        yield sse("state", "thinking")
        try:
            chunks = await rag.search(q)
        except Exception:
            log.exception("search failed")
            yield sse("state", "sad")
            yield sse("token", BUSY)
            yield sse("done", {"error": True})
            return
        if not chunks:
            yield sse("state", "sad")
            yield sse("token", NO_SOURCE)
            yield sse("done", {"sources": []})
            return

        yield sse("state", "talking")
        answer = ""
        try:
            async for part in stream_answer(SYSTEM, build_prompt(q, chunks)):
                if part is RESTART:  # model failed mid-answer, next one starts over
                    answer = ""
                    yield sse("restart", "")
                    continue
                answer += part
                if CANARY in answer:  # instructions are leaking -> stop now
                    yield sse("state", "refuse")
                    yield sse("reset", guard.REFUSAL)
                    yield sse("done", {"blocked": "leak"})
                    return
                yield sse("token", darija(part))
        except Exception:
            # never send the raw error (it can hold model names, quotas, keys...)
            log.exception("generation failed")
            yield sse("state", "sad")
            yield sse("reset", BUSY)
            yield sse("done", {"error": True})
            return

        # Only show the sources the answer actually cites
        cited = [
            c for c in chunks
            if re.search(rf"Article\s+{re.escape(c['article'].split()[1])}\b", answer, re.I)
        ]
        yield sse("state", "happy" if cited else "sad")
        yield sse("done", {
            "sources": [
                {"source": c["source"], "article": c["article"], "url": c["url"],
                 "excerpt": excerpt(c["text"])}
                for c in cited
            ]
        })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
