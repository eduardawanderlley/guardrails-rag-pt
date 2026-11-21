"""Guardrails de saída: contrato da resposta, vazamento de prompt e groundedness.

Groundedness aqui é uma aproximação lexical: a fração dos termos de cada frase da
resposta que aparece no contexto recuperado. É rápida e não depende de modelo, mas
não entende negação nem paráfrase complexa. O caminho de evolução é um juiz NLI
ou um LLM avaliador, documentado em docs/decisoes-tecnicas.md.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, ValidationError

from ..text import split_sentences, tokenize

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ModelAnswer(BaseModel):
    """Contrato que a resposta do modelo precisa cumprir antes de sair do sistema."""

    answer: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(default_factory=list)


def parse_model_output(raw: str) -> ModelAnswer | None:
    cleaned = _FENCE.sub("", raw).strip()
    try:
        return ModelAnswer.model_validate_json(cleaned)
    except ValidationError:
        return None


def find_leaks(answer: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker in answer]


def groundedness(answer: str, context: list[str]) -> float:
    context_terms = set(tokenize(" ".join(context)))
    scores: list[float] = []
    for sentence in split_sentences(answer):
        terms = tokenize(sentence)
        if terms:
            scores.append(sum(term in context_terms for term in terms) / len(terms))
    return sum(scores) / len(scores) if scores else 0.0
