from types import SimpleNamespace

from guardrails_rag.llm import AnthropicLLM, build_user_message
from guardrails_rag.models import ContextBlock
from guardrails_rag.text import normalize, tokenize


def test_normalize_removes_accents_and_case():
    assert normalize("Cartão COM Ç") == "cartao com c"


def test_tokenize_drops_stopwords_and_applies_plural_stemming():
    assert tokenize("Quais são as cobranças não contestadas?") == ["cobranca", "contestada"]


def test_user_message_marks_context_as_untrusted_and_separates_question():
    message = build_user_message("Pergunta?", [ContextBlock("doc#1", "Texto do documento.")])
    assert '<documento id="doc#1" confiavel="false">' in message
    assert "<pergunta>\nPergunta?\n</pergunta>" in message


class _FakeMessages:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        block = SimpleNamespace(type="text", text='{"answer": "ok", "source_ids": []}')
        return SimpleNamespace(content=[block])


def test_anthropic_adapter_sends_system_prompt_and_joins_text_blocks():
    fake_messages = _FakeMessages()
    client = SimpleNamespace(messages=fake_messages)
    llm = AnthropicLLM(model="modelo-teste", client=client)

    output = llm.complete("Oi?", [ContextBlock("doc#0", "Algo.")], system_prompt="SISTEMA")

    assert output == '{"answer": "ok", "source_ids": []}'
    assert fake_messages.last_kwargs["system"] == "SISTEMA"
    assert fake_messages.last_kwargs["model"] == "modelo-teste"
