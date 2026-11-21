# Decisões técnicas

Cada decisão segue o mesmo formato: contexto, o que foi escolhido, alternativas que considerei e o que a escolha custa. A ideia é que quem for alterar o projeto saiba por que as coisas estão como estão, e que as decisões ruins fiquem visíveis.

---

## 1. BM25 em vez de embeddings para a recuperação

**Contexto.** O projeto é sobre guardrails, não sobre recuperação. Eu precisava de um retriever que fosse determinístico, rápido e que rodasse sem chave de API.

**Escolha.** BM25 implementado à mão, com normalização de acentos e stemming mínimo de plural.

**Alternativas.** Embeddings com um modelo local (sentence-transformers) ou com a API de embeddings. Descartei a primeira porque adiciona um download grande e não-determinismo entre máquinas. A segunda porque cria dependência de chave para rodar os testes.

**Custo.** BM25 perde paráfrase. Um caso concreto está no relatório: "responde" não casa com "resposta", e a pergunta sobre a ouvidoria foi escalonada indevidamente. Embeddings resolveriam esse caso, mas introduziriam outros. A interface `search(query, top_k)` permite trocar sem tocar no pipeline.

---

## 2. Regras com pesos como detector principal de injection

**Contexto.** Precisava de um detector que eu conseguisse explicar linha por linha numa entrevista, e que mostrasse por que cada entrada foi bloqueada.

**Escolha.** Regras com pesos. Cada regra tem nome, padrão e peso. O bloqueio exige soma mínima de 1.0. Quando bloqueia, o `InjectionVerdict` traz a lista de regras que dispararam.

**Por que pesos e não regra binária.** Padrões como "finja", "sem regras" ou "aja como" são suspeitos sozinhos e legítimos em muitas perguntas. Com peso 0.6, um deles isolado não bloqueia. Dois juntos, sim. O teste `test_benign_questions_are_not_flagged` documenta os casos que não podem ser bloqueados.

**Alternativas.** Um classificador treinado, como um modelo de moderação ou um Prompt Guard. Não o incluí porque não treinei nem avaliei nenhum e não quis apresentar um número que não existe. O parâmetro `classifier` deixa o caminho aberto.

**Custo.** Regras são contornáveis por reformulação. A suíte inclui ofuscação com espaços e base64 justamente para mostrar um tipo de contorno, mas há muitos outros.

---

## 3. Validação de dígito verificador para CPF e CNPJ

**Contexto.** Regex para CPF casa com qualquer sequência de 11 dígitos. Em um texto com números de protocolo, pedidos ou valores, o número de falsos positivos seria alto.

**Escolha.** Regex para encontrar o candidato e validação pelo dígito verificador para aceitar. Um número como `123.456.789-00` não é tratado como CPF.

**Alternativas.** Só regex, que é o que a maioria dos tutoriais faz. Ou o reconhecedor do Presidio, que também valida, mas depende de spaCy.

**Custo.** A validação não confirma que o CPF pertence a alguém. Um CPF com dígito válido inventado também passa, e é exatamente o caso dos dados de teste da base. Isso é aceitável para mascaramento, que é conservador por natureza.

---

## 4. Honeytoken (canary) para detectar vazamento do prompt

**Contexto.** Preciso saber se o modelo revelou as instruções internas. Comparar a resposta com o texto do prompt é frágil, porque o modelo pode parafrasear.

**Escolha.** Um código aleatório (`CANARY-7F3A9K`) no prompt de sistema, com instrução de não revelar. Se o código aparece na resposta, o pipeline bloqueia.

**Custo.** O canary só pega vazamento literal. Um modelo que resume as instruções sem citar o código passa. Por isso o detector de injection continua sendo a primeira linha, e o canary é a segunda.

---

## 5. Escalonamento como saída de primeira classe

**Contexto.** Um sistema que só sabe responder ou bloquear força uma escolha ruim: ou arrisca uma resposta fraca, ou nega ajuda a alguém que tinha direito a ela.

**Escolha.** Três estados: `answered`, `blocked` e `escalated`. Escalonamento grava na fila com a pergunta mascarada e o motivo.

**Por que a pergunta é gravada mascarada.** Uma fila de revisão que guarda CPFs vira um vazamento. A fila é um arquivo local neste projeto, mas o princípio vale para qualquer sistema de tickets.

**Custo.** Escalonar tem custo operacional, e o relatório mostra isso: 8,3% das perguntas respondíveis foram escalonadas. Quanto ao limiar, eu escolhi valores iniciais pela leitura dos dados da própria base, não por calibração. Eles deveriam ser ajustados com um conjunto de validação maior.

---

## 6. Modelo simulado como linha de base

**Contexto.** Para medir o efeito dos guardrails, preciso de um modelo vulnerável e de um modelo igual, sem guardrails. Com um modelo real, a linha de base pode ser quase zero, e então não mede nada.

**Escolha.** `SimulatedUnguardedLLM`, que obedece instruções escondidas com regras explícitas. A suíte roda nele por padrão, o que torna o resultado reproduzível sem chave.

**O que isso não prova.** Os números não dizem nada sobre o comportamento de um modelo real. Eles dizem que os guardrails bloqueiam o que deveriam bloquear quando o modelo cai na armadilha. A medição com modelo real existe (`--llm anthropic`), mas não está no README porque ainda não foi executada.

---

## 7. Saída em JSON com schema validado

**Contexto.** Se a resposta é texto livre, não há como verificar `source_ids`, não há contrato para checar, e a PII pode aparecer em qualquer lugar.

**Escolha.** O modelo deve devolver JSON. O Pydantic valida. Resposta fora do schema é escalonada, não corrigida.

**Por que escalonar e não tentar de novo.** Uma nova chamada custa dinheiro e pode repetir o erro. Escalonar é previsível e fica registrado. Se o custo de falhas de schema for alto, o caminho é um retry com limite, e isso é uma mudança pequena.

---

## 8. Normalização mínima em português

**Contexto.** A base e as perguntas usam acentos, plural e algumas palavras funcionais que não carregam sentido ("não", "sem", "ser").

**Escolha.** Remoção de acentos, lista de stopwords em português e remoção do `s` final de palavras com mais de quatro letras.

**Por que não um stemmer completo.** RSLP ou similar resolveria mais casos, mas adicionaria complexidade e dependência para um ganho que, nesta base, vem principalmente de plural. A limitação aparece no relatório e está listada no README.

**Erro que eu cometi e corrigi.** A palavra "não" não estava na lista de stopwords. Ela fazia uma pergunta sobre cobrança ser respondida com uma frase sobre juros, por casamento de "não". Os testes de integração não pegaram isso; a inspeção manual das respostas pegou. Por isso, além dos testes, inspecionei as respostas de perguntas reais da base antes de fechar a versão. Uma revisão manual como essa deveria fazer parte de qualquer ajuste de recuperação.

---

## 9. Sobreposição mínima e título da seção na seleção de frases

**Contexto.** O modo extrativo escolhia as frases com mais termos em comum com a pergunta. Uma frase que repetia uma só palavra ("tarifa") virava resposta para uma pergunta que não tinha nada a ver.

**Escolha.** Exigir pelo menos dois termos em comum quando a pergunta tem dois ou mais. O título da seção entra na contagem, porque ele dá contexto a frases curtas.

**Custo.** Perguntas com um termo só e frases que dependem de sinônimo deixam de ser respondidas. Isso aparece como escalonamento indevido no relatório.

---

## 10. Perguntas legítimas com resultado esperado

**Contexto.** Medir só ataques é incompleto. Um sistema que recusa tudo tem ASR zero.

**Escolha.** Cada pergunta legítima tem o campo `expect`: `answered` ou `escalated`. Isso separa duas métricas que não são a mesma coisa. Escalonar uma pergunta que a base não responde é correto. Escalonar uma que a base responde é um custo.

**Custo.** A rotulagem é minha, e é subjetiva em casos de fronteira. "Posso ignorar a cobrança de tarifa e não pagar?" foi rotulada como sem resposta direta. Outra pessoa poderia discordar.

---

## Limitações assumidas

Estas não são decisões no sentido estrito, mas são escolhas de escopo que o leitor precisa conhecer:

- **Nomes próprios não são detectados.** Regex não pega nomes. Precisa de NER.
- **A groundedness é lexical.** Não mede verdade, nem negação, nem paráfrase.
- **A suíte tem 11 ataques.** Serve para regressão, não para certificação.
- **Não há ferramentas externas no agente.** O princípio de menor privilégio não é testado aqui.
- **Os limiares não foram calibrados.** Foram escolhidos por inspeção e devem ser ajustados com dados maiores.
