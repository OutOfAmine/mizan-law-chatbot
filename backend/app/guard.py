"""Input checks that run BEFORE the question reaches Gemini.

Not a silver bullet: prompt injection can't be fully solved by filters.
The real protection is layered: the key never leaves the server, the model
only sees retrieved official text, user text is wrapped as data, a canary
catches instruction leaks, and the answer must cite a real source.
"""
import re
import unicodedata

from .config import settings

INJECTION = [
    r"ignore (all|previous|the above|your)",
    r"(oublie|ignore)[sz]? (toutes? )?(les|tes) (instructions|r[eè]gles)",
    r"nsa (ga3 |kolchi |)(les )?(instructions|rules|9awa3id)",
    r"(system|developer|dev) (prompt|mode)",
    r"(you are|tu es|nta|انت) (now|maintenant|daba|دابا)",
    r"(api[ _-]?key|secret|token|mot de passe|password)",
    r"(show|reveal|print|3tini|عطيني|affiche).{0,30}(prompt|instructions|r[eè]gles)",
    r"تجاهل.{0,20}(التعليمات|القواعد)",
    r"انس.{0,10}(التعليمات|القواعد)",
    r"jailbreak|DAN\b|<\/?(sources|question|system)>",
]
_inj = re.compile("|".join(INJECTION), re.IGNORECASE)

REFUSAL = (
    "أنا مساعد خاص بالقانون المغربي فقط. "
    "لا يمكنني تغيير قواعدي أو مشاركة أي معلومات سرية. "
    "اسألني عن حق أو واجب في القانون."
)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # drop control + zero-width chars used to hide instructions
    text = "".join(
        ch for ch in text
        if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    return re.sub(r"\s+", " ", text).strip()


def check(question: str) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    if not question:
        return False, "empty"
    if len(question) > settings.max_question_chars:
        return False, "too_long"
    if _inj.search(question):
        return False, "injection"
    return True, ""
