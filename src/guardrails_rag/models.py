"""Estruturas de dados do pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    ANSWERED = "answered"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    score: float


@dataclass(frozen=True)
class ContextBlock:
    doc_id: str
    text: str
    title: str = ""


@dataclass(frozen=True)
class Finding:
    """Evento registrado por um guardrail durante a execução."""

    guardrail: str
    detail: str
    severity: float


@dataclass
class PipelineResult:
    status: Status
    answer: str | None
    confidence: float | None
    findings: list[Finding] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    reason: str = ""
    latency_ms: float = 0.0
