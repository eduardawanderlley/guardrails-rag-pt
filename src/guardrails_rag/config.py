"""Configuração do projeto.

Os caminhos são resolvidos a partir da raiz do repositório, então o comando
deve ser executado a partir da pasta do projeto (ou com o pacote instalado
em modo editável).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .policy import Policy

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    knowledge_base_dir: Path = ROOT / "data" / "knowledge_base"
    attacks_path: Path = ROOT / "data" / "redteam" / "attacks.yaml"
    legit_queries_path: Path = ROOT / "data" / "redteam" / "legit_queries.yaml"
    escalation_path: Path = ROOT / "runtime" / "escalations.jsonl"

    top_k: int = 3
    input_guards: bool = True
    output_guards: bool = True

    # Honeytoken: aparece apenas no prompt de sistema. Se sair na resposta, houve vazamento.
    canary_token: str = "CANARY-7F3A9K"

    llm_provider: str = "extractive"
    anthropic_model: str = "claude-haiku-5-5"

    policy: Policy = field(default_factory=Policy)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            top_k=int(os.getenv("GR_TOP_K", "3")),
            llm_provider=os.getenv("GR_LLM_PROVIDER", "extractive"),
            anthropic_model=os.getenv("GR_ANTHROPIC_MODEL", "claude-haiku-5-5"),
            policy=Policy(min_confidence=float(os.getenv("GR_MIN_CONFIDENCE", "0.6"))),
        )
