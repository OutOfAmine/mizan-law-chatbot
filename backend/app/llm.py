import asyncio
import logging

from google import genai
from google.genai import errors, types

from .config import settings

log = logging.getLogger("mizan")
_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY missing: put it in backend/.env")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _models() -> list[str]:
    chain = [settings.gemini_model] + [m.strip() for m in settings.gemini_fallbacks.split(",")]
    return list(dict.fromkeys(m for m in chain if m))


async def stream_answer(system: str, prompt: str):
    """Streams the answer. If a model is overloaded (503) or rate-limited (429)
    before it sends anything, the next model in the chain takes over."""
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        max_output_tokens=4096,  # thinking tokens count too: 1200 cut answers mid-word
    )
    last: Exception | None = None
    for model in _models():
        sent = False
        try:
            # an overloaded model can hang instead of failing: give it 15 s to start
            stream = await asyncio.wait_for(
                get_client().aio.models.generate_content_stream(model=model, contents=prompt, config=cfg),
                timeout=15,
            )
            it = stream.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(it.__anext__(), timeout=None if sent else 15)
                except StopAsyncIteration:
                    break
                parts = (chunk.candidates or [None])[0]
                text = "".join(
                    p.text for p in (parts.content.parts if parts and parts.content else []) or []
                    if getattr(p, "text", None) and not getattr(p, "thought", False)
                )
                if text:
                    sent = True
                    yield text
            if sent:
                return
            last = RuntimeError(f"{model} returned no text")
        except asyncio.TimeoutError:
            last = TimeoutError(model)
            log.warning("model %s too slow, trying next", model)
        except errors.APIError as e:
            last = e
            if e.code not in (429, 500, 503):
                raise
            log.warning("model %s unavailable (%s), trying next", model, e.code)
            if sent:
                # failed mid-answer: tell the caller to wipe the partial text,
                # then the next model writes the answer from the start
                yield RESTART
            await asyncio.sleep(0.3)
    raise last or RuntimeError("no model available")


RESTART = object()  # sentinel yielded by stream_answer


REWRITE = (
    "Transforme la question (Darija, arabe ou français) en une courte requête de recherche "
    "en français juridique, avec les termes exacts des codes marocains "
    "(ex: l7adana -> garde des enfants (hadana), tla9 -> divorce, khlass -> salaire, "
    "congé -> congé annuel payé). Donne seulement 3 à 6 mots-clés juridiques, sans le nom du code, sans 'Maroc' ni 'marocain', sans explication."
)


async def rewrite_query(question: str) -> str:
    """Darija -> French legal keywords, so the search matches the official text.
    The output is only used as a search query, never shown or obeyed."""
    for model in dict.fromkeys([settings.rewrite_model, "gemini-3.5-flash-lite"]):
        try:
            res = await asyncio.wait_for(get_client().aio.models.generate_content(
                model=model,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=REWRITE, temperature=0, max_output_tokens=200,
                ),
            ), timeout=7)
            text = "".join(p.text for p in res.candidates[0].content.parts if getattr(p, "text", None))
            return text.strip()[:200]
        except Exception as e:  # try the next model; search still works with the raw question
            log.warning("rewrite with %s failed: %s", model, str(e)[:80])
    return ""
