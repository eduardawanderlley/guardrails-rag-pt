"""Detecção de prompt injection e jailbreak.

Três camadas, em ordem:
1. Regras com pesos (PT-BR e EN), aplicadas após normalizar o texto
   (NFKC, caracteres invisíveis removidos, acentos removidos).
2. Conteúdo codificado em base64 é decodificado e analisado com as mesmas regras.
   Texto com letras separadas por espaços ou pontuação é verificado sem separadores.
3. Classificador externo opcional, passado como função que devolve uma probabilidade.

O texto é considerado injeção quando a soma dos pesos atinge o limiar (padrão: 1.0).
Um peso isolado de 0.5 ou 0.6 não basta, o que evita bloquear perguntas legítimas
que apenas contenham uma palavra suspeita como "finja" ou "sem".
"""

from __future__ import annotations

import base64
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from ..text import normalize

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/])")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    weight: float


RULES: tuple[Rule, ...] = (
    Rule(
        "ignorar_instrucoes",
        re.compile(
            r"\b(ignor\w*|desconsider\w*|disregard\w*|esquec\w*|forget)\b\s+(\w+\s+){0,3}?"
            r"(instrucoes|instructions|regras|rules|prompt)\b"
        ),
        1.0,
    ),
    Rule(
        "revelar_prompt",
        re.compile(
            r"\b(revel\w*|mostr\w*|exib\w*|imprim\w*|repit\w*|reveal|show|print|repeat|display)\b\s+"
            r"(\w+\s+){0,4}?(prompt|mensagem de sistema|instrucoes de sistema|instrucoes do sistema"
            r"|system (prompt|message|instructions))\b"
        ),
        1.0,
    ),
    Rule("marcador_de_papel", re.compile(r"^\s*(system|assistant)\s*:", re.MULTILINE), 1.0),
    Rule("tag_de_controle", re.compile(r"</?\s*(system|instructions|instrucoes)\s*>"), 1.0),
    Rule(
        "troca_de_papel",
        re.compile(
            r"\b(finja|finge|aja como|act as|pretend (to be|you are)|voce agora e|you are now"
            r"|modo desenvolvedor|developer mode|jailbreak)\b"
        ),
        0.6,
    ),
    Rule(
        "sem_restricoes",
        re.compile(r"\b(sem|without|no)\s+(regras|restricoes|limites|filtros|censura|rules|restrictions|filters)\b"),
        0.6,
    ),
    Rule(
        "comando_de_resposta",
        re.compile(r"\b(responda|respond|reply|say)\b\s*(apenas|somente|only)?\s*(com|with)?\s*:"),
        0.5,
    ),
)

# Sem espaços nem pontuação, o texto "i g n o r e" vira "ignore" e as regras acima o pegam.
_SQUASHED_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignorar_instrucoes", re.compile(r"(ignor|desconsider|disregard)[a-z]{0,6}(instru|regras|rules)")),
    ("revelar_prompt", re.compile(r"(revel|mostr|reveal|show|print)[a-z]{0,8}prompt")),
)


@dataclass(frozen=True)
class InjectionVerdict:
    is_injection: bool
    score: float
    matched: tuple[str, ...]


def _clean(text: str) -> str:
    without_hidden = _ZERO_WIDTH.sub("", text)
    return normalize(unicodedata.normalize("NFKC", without_hidden))


def _decode_base64_blobs(text: str) -> list[str]:
    blobs: list[str] = []
    for candidate in _BASE64.findall(text):
        try:
            blobs.append(base64.b64decode(candidate, validate=True).decode("utf-8"))
        except ValueError:
            continue
    return blobs


def _scan(text: str, prefix: str = "") -> tuple[list[str], float]:
    matched: list[str] = []
    score = 0.0
    for rule in RULES:
        if rule.pattern.search(text):
            matched.append(f"{prefix}{rule.name}")
            score += rule.weight
    return matched, score


class InjectionDetector:
    def __init__(
        self,
        threshold: float = 1.0,
        classifier: Callable[[str], float] | None = None,
        classifier_threshold: float = 0.8,
    ) -> None:
        self._threshold = threshold
        self._classifier = classifier
        self._classifier_threshold = classifier_threshold

    def inspect(self, text: str) -> InjectionVerdict:
        normalized = _clean(text)
        matched, score = _scan(normalized)

        for decoded in _decode_base64_blobs(text):
            found, weight = _scan(_clean(decoded), prefix="base64:")
            matched.extend(found)
            score += weight

        if score < self._threshold:
            squashed = _NON_ALNUM.sub("", normalized)
            for name, pattern in _SQUASHED_RULES:
                if pattern.search(squashed):
                    matched.append(f"ofuscado:{name}")
                    score += 1.0

        if self._classifier is not None and self._classifier(text) >= self._classifier_threshold:
            matched.append("classificador")
            score += 1.0

        return InjectionVerdict(
            is_injection=score >= self._threshold,
            score=round(score, 2),
            matched=tuple(matched),
        )
