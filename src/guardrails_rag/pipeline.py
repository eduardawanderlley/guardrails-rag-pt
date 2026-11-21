"""Pipeline do assistente.

Fluxo para cada pergunta:

    pergunta
      -> detecção de injection na entrada (bloqueia)
      -> mascaramento de PII na entrada
      -> recuperação BM25
      -> detecção de injection em cada documento recuperado (descarta o documento)
      -> geração com o contexto delimitado como não confiável
      -> validação do schema da saída (escalona se inválido)
      -> bloqueio se o prompt de sistema vazou (canary)
      -> mascaramento de PII na saída
      -> groundedness e confiança: responde ou escalona

Com input_guards e output_guards desligados, o pipeline vira a linha de base:
recuperação e geração, sem nenhuma verificação. É contra ela que medimos os guardrails.
"""

from __future__ import annotations

import json
from time import perf_counter

from .config import Settings
from .escalation import EscalationQueue
from .guardrails.injection import InjectionDetector
from .guardrails.output import find_leaks, groundedness, parse_model_output
from .guardrails.pii import PIIDetector
from .llm import LLMClient, build_system_prompt
from .models import ContextBlock, Finding, PipelineResult, RetrievedChunk, Status
from .policy import combined_confidence, decide, retrieval_strength
from .retrieval import BM25Retriever


class GuardedRAG:
    def __init__(
        self,
        retriever: BM25Retriever,
        llm: LLMClient,
        settings: Settings,
        *,
        injection: InjectionDetector | None = None,
        pii: PIIDetector | None = None,
        escalation: EscalationQueue | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._settings = settings
        self._injection = injection or InjectionDetector()
        self._pii = pii or PIIDetector()
        self._escalation = escalation
        self._system_prompt = build_system_prompt(settings.canary_token)

    def ask(self, question: str) -> PipelineResult:
        started = perf_counter()
        result = self._answer(question)
        result.latency_ms = round((perf_counter() - started) * 1000, 2)
        return result

    def _answer(self, question: str) -> PipelineResult:
        settings = self._settings
        findings: list[Finding] = []

        query = question
        if settings.input_guards:
            verdict = self._injection.inspect(question)
            if verdict.is_injection:
                findings.append(Finding("prompt_injection", ", ".join(verdict.matched), verdict.score))
                return PipelineResult(
                    Status.BLOCKED, None, 0.0, findings, reason="tentativa de prompt injection na entrada"
                )
            query, input_pii = self._pii.mask(question)
            findings.extend(Finding("pii_input", match.entity, 1.0) for match in input_pii)

        chunks = self._retriever.search(query, top_k=settings.top_k)
        if settings.input_guards:
            chunks = self._drop_injected_chunks(chunks, findings)
            if not chunks:
                return self._escalate(query, "nenhum contexto confiável recuperado", 0.0, [], findings)

        context = [
            ContextBlock(chunk.document.doc_id, chunk.document.text, chunk.document.title) for chunk in chunks
        ]
        context_ids = [chunk.document.doc_id for chunk in chunks]
        raw = self._llm.complete(query, context, self._system_prompt)

        if not settings.output_guards:
            return PipelineResult(
                Status.ANSWERED,
                _unwrap_answer(raw),
                None,
                findings,
                citations=context_ids,
                reason="sem guardrails (linha de base)",
            )

        parsed = parse_model_output(raw)
        if parsed is None:
            return self._escalate(query, "saída do modelo fora do schema esperado", 0.0, context_ids, findings)

        if find_leaks(parsed.answer, [settings.canary_token]):
            findings.append(Finding("output_leak", "marcador interno presente na resposta", 1.0))
            return PipelineResult(Status.BLOCKED, None, 0.0, findings, reason="vazamento do prompt de sistema")

        citations = [source for source in parsed.source_ids if source in context_ids]
        if len(citations) != len(parsed.source_ids):
            findings.append(Finding("output_schema", "source_ids fora do contexto foram removidos", 0.5))

        answer, output_pii = self._pii.mask(parsed.answer)
        findings.extend(Finding("pii_output", match.entity, 1.0) for match in output_pii)

        grounded = groundedness(answer, [block.text for block in context])
        strength = retrieval_strength(chunks[0].score, settings.policy.retrieval_reference)
        confidence = combined_confidence(strength, grounded, settings.policy)
        status, reason = decide(strength, confidence, grounded, settings.policy)

        if status is Status.ESCALATED:
            return self._escalate(query, reason, confidence, context_ids, findings)
        return PipelineResult(Status.ANSWERED, answer, confidence, findings, citations, reason)

    def _drop_injected_chunks(self, chunks: list[RetrievedChunk], findings: list[Finding]) -> list[RetrievedChunk]:
        trusted: list[RetrievedChunk] = []
        for chunk in chunks:
            verdict = self._injection.inspect(chunk.document.text)
            if verdict.is_injection:
                detail = f"{chunk.document.doc_id} descartado ({', '.join(verdict.matched)})"
                findings.append(Finding("indirect_injection", detail, verdict.score))
            else:
                trusted.append(chunk)
        return trusted

    def _escalate(
        self,
        question: str,
        reason: str,
        confidence: float,
        context_ids: list[str],
        findings: list[Finding],
    ) -> PipelineResult:
        if self._escalation is not None:
            self._escalation.enqueue(
                question=question, reason=reason, confidence=confidence, context_ids=context_ids
            )
        return PipelineResult(Status.ESCALATED, None, confidence, findings, reason=reason)


def _unwrap_answer(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(payload, dict) and isinstance(payload.get("answer"), str):
        return payload["answer"]
    return raw
