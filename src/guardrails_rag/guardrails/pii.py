"""Detecção e mascaramento de dados pessoais, com foco em identificadores brasileiros.

CPF e CNPJ são validados pelo dígito verificador. Só a regex gera muitos falsos
positivos, porque qualquer sequência de 11 dígitos parece um CPF.

RG só é detectado quando precedido pelo rótulo "RG", porque o formato varia por
estado e um padrão sem contexto geraria muito ruído.

Este módulo não depende de spaCy nem de modelos NLP. A arquitetura aceita trocar
este detector pelo Microsoft Presidio. Veja docs/decisoes-tecnicas.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIMatch:
    entity: str
    start: int
    end: int
    value: str


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _cpf_check_digit(digits: str, length: int) -> int:
    total = sum(int(d) * (length + 1 - i) for i, d in enumerate(digits[:length]))
    return (total * 10 % 11) % 10


def is_valid_cpf(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    return _cpf_check_digit(digits, 9) == int(digits[9]) and _cpf_check_digit(digits, 10) == int(digits[10])


_CNPJ_FIRST_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_SECOND_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _cnpj_check_digit(digits: str, weights: tuple[int, ...]) -> int:
    rest = sum(int(d) * w for d, w in zip(digits, weights)) % 11
    return 0 if rest < 2 else 11 - rest


def is_valid_cnpj(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    return (
        _cnpj_check_digit(digits[:12], _CNPJ_FIRST_WEIGHTS) == int(digits[12])
        and _cnpj_check_digit(digits[:13], _CNPJ_SECOND_WEIGHTS) == int(digits[13])
    )


_CNPJ_RE = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_RG_RE = re.compile(r"\bRG\b[:\s]*\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX](?!\w)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55[\s-]?)?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}(?!\d)")

# A ordem define a prioridade quando dois padrões disputam o mesmo trecho.
_RECOGNIZERS: tuple[tuple[str, re.Pattern[str], Callable[[str], bool] | None], ...] = (
    ("CNPJ", _CNPJ_RE, is_valid_cnpj),
    ("CPF", _CPF_RE, is_valid_cpf),
    ("RG", _RG_RE, None),
    ("EMAIL", _EMAIL_RE, None),
    ("TELEFONE", _PHONE_RE, None),
)


def _overlaps(a: PIIMatch, b: PIIMatch) -> bool:
    return a.start < b.end and b.start < a.end


class PIIDetector:
    def find(self, text: str) -> list[PIIMatch]:
        accepted: list[PIIMatch] = []
        for entity, pattern, validator in _RECOGNIZERS:
            for match in pattern.finditer(text):
                value = match.group(0)
                if validator is not None and not validator(value):
                    continue
                candidate = PIIMatch(entity, match.start(), match.end(), value)
                if not any(_overlaps(candidate, other) for other in accepted):
                    accepted.append(candidate)
        return sorted(accepted, key=lambda m: m.start)

    def mask(self, text: str) -> tuple[str, list[PIIMatch]]:
        matches = self.find(text)
        masked = text
        for match in reversed(matches):
            masked = f"{masked[:match.start]}[{match.entity}]{masked[match.end:]}"
        return masked, matches
