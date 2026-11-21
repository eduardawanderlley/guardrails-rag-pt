"""Fila de revisão humana.

Cada escalonamento vira uma linha JSON com a pergunta já mascarada, o motivo, a
confiança e os documentos consultados. O formato é JSONL para que a fila possa ser
lida por qualquer ferramenta, ou enviada a um sistema de tickets sem transformação.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EscalationQueue:
    def __init__(self, path: Path) -> None:
        self._path = path

    def enqueue(
        self,
        *,
        question: str,
        reason: str,
        confidence: float,
        context_ids: list[str],
    ) -> dict[str, Any]:
        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "reason": reason,
            "confidence": confidence,
            "context_ids": context_ids,
            "status": "pending",
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def pending(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
