"""Utilitários de texto usados pela recuperação e pelos guardrails."""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[a-z0-9]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

STOPWORDS = frozenset(
    {
        "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "um", "uma",
        "para", "por", "com", "que", "se", "no", "na", "nos", "nas", "ao", "aos", "ou",
        "como", "qual", "quais", "meu", "minha", "seu", "sua", "eu", "voce", "pode",
        "posso", "sobre", "isso", "esta", "este", "ha", "the", "is", "of", "to", "in",
        "and", "what", "how", "do", "my",
        "nao", "sao", "ser", "foi", "ele", "ela", "isto", "tem", "ter", "mais", "muito",
        "ja", "tambem", "mas", "pelo", "pela", "pelos", "pelas", "entre", "sem",
    }
)


def normalize(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _strip_plural(token: str) -> str:
    """Stemming mínimo: remove o 's' final de plurais ("cobranças" -> "cobranca").

    Não é um stemmer completo. Um RSLP completo cobriria mais casos, mas para esta
    base o plural é a principal fonte de falha de casamento lexical.
    """
    return token[:-1] if len(token) > 4 and token.endswith("s") else token


def tokenize(text: str) -> list[str]:
    """Tokeniza, remove stopwords e tokens de um caractere, e aplica stemming mínimo de plural."""
    tokens = (t for t in _WORD_RE.findall(normalize(text)) if len(t) > 1 and t not in STOPWORDS)
    return [_strip_plural(t) for t in tokens]


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_RE.split(text) if part and part.strip()]
