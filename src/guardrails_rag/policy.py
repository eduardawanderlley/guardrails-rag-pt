"""Política de decisão: responder, bloquear ou encaminhar para revisão humana.

A decisão combina três sinais:
- força da recuperação (o quão forte foi o melhor documento encontrado);
- groundedness (quanto da resposta se apoia no contexto recuperado);
- confiança combinada, média ponderada dos dois sinais anteriores.

Se qualquer um estiver abaixo do limiar, a pergunta vai para a fila de revisão.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Status


@dataclass(frozen=True)
class Policy:
    min_retrieval_strength: float = 0.35
    min_groundedness: float = 0.6
    min_confidence: float = 0.6
    retrieval_reference: float = 6.0
    retrieval_weight: float = 0.4


def retrieval_strength(top_score: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return min(1.0, max(0.0, top_score / reference))


def combined_confidence(strength: float, groundedness: float, policy: Policy) -> float:
    weight = policy.retrieval_weight
    return round(weight * strength + (1 - weight) * groundedness, 3)


def decide(strength: float, confidence: float, groundedness: float, policy: Policy) -> tuple[Status, str]:
    if strength < policy.min_retrieval_strength:
        return Status.ESCALATED, "contexto pouco relevante para a pergunta"
    if groundedness < policy.min_groundedness:
        return Status.ESCALATED, "resposta pouco fundamentada nos documentos"
    if confidence < policy.min_confidence:
        return Status.ESCALATED, "confiança abaixo do limiar"
    return Status.ANSWERED, "resposta dentro dos critérios de confiança"
