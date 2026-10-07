# T08 — Agentes ADK (root + especialistas)

**Depende de**: T04 (topologia decidida!), T05, T06, T07. **Bloqueia**: T09.

## Objetivo

Montar o agente principal e os 3 especialistas (reservas, visitantes, regulamento), usando
exatamente a topologia de acionamento que `T04` validou funcionar com sessão persistida e resume
de confirmação.

## Passos

1. `app/agents/especialista_reservas.py`: agente com as tools de `app/agents/tools/reservas_tools.py`
   (`T05`). Instruções só sobre reservas (área, data, disponibilidade, cancelamento) — nada de
   regulamento, nada de visitantes.
2. `app/agents/especialista_visitantes.py`: agente com as tools de `visitantes_tools.py` (`T06`).
3. `app/agents/especialista_regulamento.py`: agente com a tool de `regulamento_tools.py` (`T07`).
   Instruções dizem pra sempre usar a tool de busca antes de responder, nunca responder de
   memória própria sobre o regulamento.
4. `app/agents/root_agent.py`: agente principal.
   - **Instruções não contêm nenhum trecho do regulamento** — só descrevem que existem 3
     especialistas e quando rotear pra cada um (critério por assunto da mensagem).
   - Acionamento dos especialistas usa a topologia validada em `T04` (sub_agents com transfer, ou
     AgentTool — o que tiver funcionado no spike).
   - Agente principal não declara tools de negócio direto (reservar, autorizar, cancelar) — essas
     ficam só nos especialistas, para manter a responsabilidade de cada tool isolada por domínio
     (boa prática de tools do curso).

## Entregáveis

- Os 4 arquivos de agente em `app/agents/`.

## Critério de aceite

- Uma conversa que mistura assuntos (pergunta de regulamento, depois pede reserva) roteia pro
  especialista certo em cada turno.
- Grep em `app/agents/root_agent.py` não encontra nenhum trecho do texto de
  `dados/regulamento.md` (confirma o requisito literal da Garantia 4 e do passo 15 do fluxo do
  avaliador).
- Uma tool pausada por confirmação em um especialista, depois de uma resposta de confirmação
  injetada pelo Runner (ver `T09`), retoma no mesmo especialista, não no root nem em outro
  especialista — repetir o teste de restart do `T04` agora com a topologia completa dos 3
  especialistas.
