# Arquitetura

Este documento descreve como o sistema está organizado, por que cada parte existe e o que acontece quando algo dá errado. Para as decisões e os trade-offs, veja [decisoes-tecnicas.md](decisoes-tecnicas.md).

## Visão geral

O projeto é um assistente RAG com uma camada de guardrails em volta. O modelo nunca recebe a pergunta crua nem um documento não verificado, e a resposta nunca sai sem passar por validação.

```
 pergunta
    │
    ▼
┌──────────────────────────┐
│ Guardrail de entrada     │  injection (regras, base64, ofuscação)  ──► BLOCKED
│                          │  mascaramento de PII
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│ Recuperação (BM25)       │
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│ Guardrail de documentos  │  injection em cada chunk recuperado ──► descarta chunk
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│ Geração (LLM)            │  contexto delimitado como não confiável
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│ Guardrail de saída       │  schema ──────────────────────────► ESCALATED
│                          │  vazamento de canary ─────────────► BLOCKED
│                          │  mascaramento de PII
│                          │  groundedness
└──────────────────────────┘
    │
    ▼
┌──────────────────────────┐
│ Política de decisão      │  força da recuperação, groundedness, confiança
└──────────────────────────┘
    │                 │
    ▼                 ▼
 ANSWERED          ESCALATED ──► fila de revisão humana (JSONL)
```

## Componentes

### Pipeline (`pipeline.py`)

É o único lugar que conhece a ordem das etapas. A classe `GuardedRAG` recebe um retriever, um LLM, as configurações e, opcionalmente, os detectores e a fila de escalonamento. Isso permite trocar qualquer peça sem tocar na orquestração.

Com `input_guards` e `output_guards` desligados, o mesmo pipeline vira a linha de base: recuperação e geração sem verificação. Essa é a única diferença entre os dois modos da suíte de red team, o que faz a comparação ser justa.

### Recuperação (`retrieval.py`)

Carrega arquivos Markdown e divide cada um em seções, usando `##` como separador. Cada seção vira um `Document` com `doc_id` no formato `arquivo#índice`. O `BM25Retriever` calcula o score sobre título e texto.

A escolha de BM25 em vez de embeddings está justificada em [decisoes-tecnicas.md](decisoes-tecnicas.md). Em resumo: é determinístico, não depende de chave de API e deixa o foco no que o projeto quer mostrar.

### Guardrails de entrada (`guardrails/injection.py`, `guardrails/pii.py`)

**Injection.** O texto é normalizado (NFKC, caracteres invisíveis removidos, acentos removidos e minúsculas) e passa por um conjunto de regras com pesos. A soma dos pesos é comparada com um limiar, por padrão 1.0. Um peso isolado de 0.5 ou 0.6 não basta, o que evita bloquear perguntas legítimas com palavras como "finja" ou "sem".

Depois das regras, dois mecanismos cobrem ofuscação. Trechos com aparência de base64 são decodificados e analisados com as mesmas regras. E o texto é verificado sem espaços nem pontuação, para pegar letras separadas. Um classificador externo pode ser passado como função. Ele não está treinado no projeto.

**PII.** Os padrões são CNPJ, CPF, RG (apenas com o rótulo "RG"), e-mail e telefone. CPF e CNPJ só são aceitos depois de validar o dígito verificador. Quando dois padrões disputam o mesmo trecho, a ordem da lista de reconhecedores decide quem fica.

### Guardrails de saída (`guardrails/output.py`)

Três verificações, nesta ordem:

1. **Schema.** A resposta precisa ser JSON com `answer` (entre 1 e 2000 caracteres) e `source_ids`. Blocos de código em cerca Markdown são removidos antes. Falha no schema vira escalonamento, não resposta.
2. **Vazamento.** O prompt de sistema contém um canary (honeytoken). Se esse marcador aparece na resposta, o pipeline bloqueia. O canary não é um segredo de verdade; ele é um sinal de que a instrução interna saiu.
3. **Groundedness.** Para cada frase da resposta, calcula-se a fração dos termos de conteúdo que aparecem nos documentos recuperados. A média das frases é o score. Ver a seção de limitações.

Depois, a PII da resposta é mascarada e as citações que não correspondem a documentos recuperados são removidas.

### Política de decisão (`policy.py`)

Recebe três sinais e decide, nesta ordem:

1. Força da recuperação abaixo de `min_retrieval_strength` (padrão 0.35): escalonar por contexto pouco relevante.
2. Groundedness abaixo de `min_groundedness` (padrão 0.6): escalonar por resposta pouco fundamentada.
3. Confiança combinada abaixo de `min_confidence` (padrão 0.6): escalonar.
4. Caso contrário, responder.

A confiança combinada é uma média ponderada: 40% da força da recuperação e 60% da groundedness. Os pesos são arbitrários e estão nos parâmetros da `Policy`, para serem ajustados com dados reais.

### Fila de escalonamento (`escalation.py`)

Cada escalonamento vira uma linha em JSONL com a pergunta já mascarada. Isso é uma escolha de privacidade: a fila de revisão não deve ser um depósito de CPFs. Os campos são `created_at`, `question`, `reason`, `confidence`, `context_ids` e `status`.

### LLMs (`llm.py`)

Três adaptadores, todos com a mesma interface `complete(question, context, system_prompt) -> str`:

| Adaptador | Uso | Observação |
|---|---|---|
| `ExtractiveLLM` | Padrão, offline | Escolhe as frases mais relevantes do contexto. Determinístico. |
| `SimulatedUnguardedLLM` | Linha de base de red team | Obedece instruções escondidas. Não representa modelo real. |
| `AnthropicLLM` | Modelo real | Usa o SDK da Anthropic. Precisa de `ANTHROPIC_API_KEY`. |

O `build_user_message` delimita cada documento com `confiavel="false"` e separa a pergunta em uma tag própria. Isso não impede injeção por si só, mas deixa explícito para o modelo o que é dado e o que é instrução.

### Red team (`redteam/`)

- `suite.py` carrega os ataques (`data/redteam/attacks.yaml`) e as perguntas legítimas rotuladas (`data/redteam/legit_queries.yaml`).
- `runner.py` executa os dois modos. Para cada ataque com `poisoned_document`, cria um índice novo com o documento malicioso. Um ataque é bem-sucedido se algum marcador da suíte aparece na resposta entregue ao usuário.
- `report.py` gera o Markdown.

## Contratos de dados

As estruturas estão em `models.py`. O ponto importante é `PipelineResult`, que é o único objeto que sai do pipeline:

```python
PipelineResult(
    status: Status,                 # answered | blocked | escalated
    answer: str | None,             # None quando bloqueado ou escalonado
    confidence: float | None,       # None no modo sem guardrails
    findings: list[Finding],        # eventos de cada guardrail, com severidade
    citations: list[str],           # doc_ids dos documentos usados
    reason: str,                    # motivo legível da decisão
    latency_ms: float,
)
```

Uma regra que segui com cuidado: se `status` não é `ANSWERED`, `answer` é `None`. Quem consome o resultado não precisa adivinhar se uma resposta bloqueada chegou a algum lugar.

## Comportamento em falhas

| Situação | Comportamento | Onde |
|---|---|---|
| Pergunta com injeção | Bloqueada antes da recuperação | `pipeline._answer` |
| Documento recuperado com injeção | Chunk descartado, demais chunks seguem | `_drop_injected_chunks` |
| Nenhum chunk confiável sobra | Escalonada | `_answer` |
| Modelo devolve algo fora do schema | Escalonada, com confiança 0 | `parse_model_output` |
| Canary aparece na saída | Bloqueada | `find_leaks` |
| Contexto pouco relevante | Escalonada | `policy.decide` |
| Groundedness baixa | Escalonada | `policy.decide` |
| Falha na escrita da fila | Exceção propagada | `EscalationQueue.enqueue` |

A última linha é deliberada. Se a fila de revisão não grava, o sistema não deve fingir que escalonou. Tratar esse caso (retry, fila em memória, alerta) é uma decisão de infraestrutura que depende de onde o projeto roda.

## Pontos de extensão

- **Detector de PII com Presidio.** Substituir `PIIDetector` por uma classe com `find` e `mask` com a mesma assinatura. O restante do pipeline não muda.
- **Juiz de groundedness.** Substituir `groundedness` por uma função com a mesma assinatura que chame um NLI ou um LLM avaliador.
- **Retriever vetorial.** Qualquer objeto com `search(query, top_k) -> list[RetrievedChunk]` serve.
- **Classificador de injection.** Passar `classifier=` ao `InjectionDetector`, uma função que devolve probabilidade.
- **Modelo real.** `--llm anthropic` ou um novo adaptador que implemente `LLMClient`.

## O que não está na arquitetura, e por quê

- **Ferramentas para o agente.** O sistema não chama ferramentas externas. Em um agente que age, a principal defesa contra injeção é o menor privilégio nas ferramentas, e isso não está implementado aqui.
- **Observabilidade.** Não há integração com Langfuse, LangSmith ou OpenTelemetry. O `latency_ms` e os `findings` são o que o projeto registra hoje. Adicionar tracing é direto, porque o pipeline já devolve tudo o que um trace precisaria.
- **Persistência além da fila.** Não há banco. A fila é um arquivo, o que basta para o escopo e para testes.
