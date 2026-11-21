"""Carregamento da suíte de red team e das perguntas legítimas.

As perguntas legítimas existem para medir falsos positivos. Bloquear tudo também
é uma falha, e só a suíte de ataques não mostra isso.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PoisonedDocument:
    """Documento malicioso inserido no índice para simular injeção indireta."""

    title: str
    text: str


@dataclass(frozen=True)
class Attack:
    attack_id: str
    category: str
    description: str
    question: str
    success_markers: tuple[str, ...]
    poisoned_document: PoisonedDocument | None = None


def load_attacks(path: Path) -> list[Attack]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    attacks: list[Attack] = []
    for item in raw["attacks"]:
        poison = item.get("poisoned_document")
        attacks.append(
            Attack(
                attack_id=item["id"],
                category=item["category"],
                description=item["description"],
                question=item["question"],
                success_markers=tuple(item["success_markers"]),
                poisoned_document=PoisonedDocument(poison["title"], poison["text"]) if poison else None,
            )
        )
    return attacks


@dataclass(frozen=True)
class LegitQuery:
    query: str
    expect: str  # "answered" ou "escalated"


def load_legit_queries(path: Path) -> list[LegitQuery]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [LegitQuery(query=item["query"], expect=item["expect"]) for item in raw["queries"]]
