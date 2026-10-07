# Visão geral — Assistente do Residencial Aurora

## Objetivo

Construir, com Google ADK, o assistente de chat do Residencial Aurora exposto por uma API
Python/FastAPI em `http://localhost:8000`, garantindo que cinco regras críticas (confirmação,
isolamento por sessão/apartamento, persistência, RAG do regulamento e exclusividade de reserva)
estejam implementadas **em código**, não dependentes do que o modelo decide.

Enunciado completo: [`ENUNCIADO.md`](../ENUNCIADO.md) (não editar — é a fonte da verdade do contrato
e dos critérios de aceite).

## Como usar esta pasta

- [`01-decisoes.md`](01-decisoes.md) — decisões de arquitetura já tomadas (ADRs curtos), com o porquê.
- [`02-arquitetura.md`](02-arquitetura.md) — visão de componentes, agentes, fluxo de dados.
- [`03-modelo-dados.md`](03-modelo-dados.md) — contratos de schema/função entre módulos, para permitir
  trabalho paralelo sem integração quebrar no final.
- [`04-plano-testes.md`](04-plano-testes.md) — como validar as 5 garantias, baseado nos 15 passos do
  "Fluxo do avaliador" do enunciado.
- [`05-riscos.md`](05-riscos.md) — riscos conhecidos e como mitigá-los antes de depender deles.
- [`tasks/`](tasks/README.md) — backlog com um arquivo por tarefa (ID, dependências, contratos de
  entrada/saída, critérios de aceite), pensado para ser pego por agentes/sessões diferentes em paralelo.

## Regra de ouro do desafio

> O modelo decide o caminho, o código decide o que é permitido.

Qualquer decisão de implementação que viole isso (ex.: tool que aceita `apartamento` como argumento
do modelo, ou confirmação resolvida por texto da conversa) é bug, não escolha de design.
