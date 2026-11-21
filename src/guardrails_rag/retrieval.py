"""Recuperação lexical com BM25 sobre a base de conhecimento.

Escolhi BM25 em vez de embeddings para este projeto: é determinístico, não exige
chave de API nem modelo baixado, e o foco aqui são os guardrails, não a recuperação.
A interface é simples o bastante para trocar por um retriever vetorial depois.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .models import Document, RetrievedChunk
from .text import tokenize


def load_knowledge_base(directory: Path) -> list[Document]:
    """Carrega arquivos Markdown e divide cada arquivo em seções (um '##' por documento)."""
    documents: list[Document] = []
    for path in sorted(directory.glob("*.md")):
        for index, section in enumerate(path.read_text(encoding="utf-8").split("\n## ")):
            body = section.strip()
            if not body:
                continue
            heading, _, content = body.partition("\n")
            if not content.strip():
                continue  # seção só com título (ex.: o H1 do arquivo) não é um documento útil
            title = heading.lstrip("# ").strip() or path.stem
            documents.append(Document(doc_id=f"{path.stem}#{index}", title=title, text=content.strip()))
    return documents


class BM25Retriever:
    def __init__(self, documents: Iterable[Document], k1: float = 1.5, b: float = 0.75) -> None:
        self._documents = list(documents)
        self._k1 = k1
        self._b = b
        self._term_freqs: list[Counter[str]] = []
        self._lengths: list[int] = []

        document_frequency: Counter[str] = Counter()
        for doc in self._documents:
            tokens = tokenize(f"{doc.title} {doc.text}")
            freqs = Counter(tokens)
            self._term_freqs.append(freqs)
            self._lengths.append(len(tokens))
            document_frequency.update(freqs.keys())

        total = len(self._documents)
        self._avg_length = (sum(self._lengths) / total) if total else 0.0
        self._idf = {
            term: math.log(1 + (total - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        terms = set(tokenize(query))
        scored: list[RetrievedChunk] = []
        for doc, freqs, length in zip(self._documents, self._term_freqs, self._lengths):
            score = 0.0
            for term in terms:
                freq = freqs.get(term)
                if not freq:
                    continue
                norm = freq + self._k1 * (1 - self._b + self._b * length / self._avg_length)
                score += self._idf[term] * freq * (self._k1 + 1) / norm
            if score > 0:
                scored.append(RetrievedChunk(document=doc, score=round(score, 4)))
        scored.sort(key=lambda chunk: chunk.score, reverse=True)
        return scored[:top_k]
