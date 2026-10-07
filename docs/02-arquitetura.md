# Arquitetura

## Componentes

```
                         ┌─────────────────────────┐
  HTTP cliente  ───────▶ │   FastAPI (app/main.py)  │
                         │  6 rotas do contrato      │
                         └──────────┬───────────────┘
                                    │
                         ┌──────────▼───────────────┐
                         │  adk_runtime.py            │
                         │  Runner + App              │
                         │  SqliteSessionService     │──▶ data/aurora_sessions.db
                         │  resumo de confirmação       │
                         └──────────┬───────────────┘
                                    │
                    ┌───────────────┼────────────────────┐
                    ▼               ▼                    ▼
           especialista_      especialista_        especialista_
           reservas           visitantes           regulamento
                │                   │                    │
           tools reservas      tools visitantes     tool busca_regulamento
                │                   │                    │
                └─────────┬─────────┘                    ▼
                          ▼                         regulamento/index.py
                  db/condo_repo.py                  (embeddings em memória,
                          │                          cache em disco)
                          ▼
                 data/aurora_condo.db
         (reservas, visitantes, confirmacoes, contador)

           agente principal (root_agent) roteia para os 3 especialistas,
           sem regulamento nas instruções, sem tools de negócio direto.
```

## Fluxo de uma mensagem

1. `POST /sessoes/{id}/mensagens` chama `adk_runtime.enviar_mensagem(session_id, texto)`.
2. O Runner executa o turno. O agente principal decide qual especialista chamar.
3. Se uma tool do especialista exigir confirmação (criar reserva com taxa, autorizar visitante):
   - a execução pausa; gravamos uma linha em `confirmacoes` (status `pending`) com os argumentos
     reais da tool (`area`/`data` ou `nome`/`data`);
   - a resposta HTTP devolve `resposta=""` e a lista de pendências.
4. Se nenhuma tool pedir confirmação, a resposta final do agente principal volta em `resposta`.
5. `confirmacoes_pendentes` na resposta é sempre recalculado consultando a tabela `confirmacoes`
   filtrada por `session_id` e `status='pending'` — nunca é estado implícito do modelo.

## Fluxo de confirmação

1. `POST /sessoes/{id}/confirmacoes {"id", "confirmado"}`.
2. Lookup em `confirmacoes` por `id` + `session_id` com `status='pending'`. Não existe → `409`.
3. Transação: marca a linha como `approved`/`denied` **antes** de tocar no Runner (evita execução
   dupla em reenvio, mesmo sob corrida).
4. Se `confirmado=true`, injeta a resposta de confirmação no Runner pelo mecanismo nativo do ADK,
   retomando a execução da tool pausada no agente que a solicitou. Se `false`, não chama o Runner
   para executar nada — só registra a negação.
5. Resposta HTTP no mesmo formato da rota de mensagens.

## Isolamento por apartamento (Garantia 2)

- `session.state["apartamento"]` é escrito uma vez, em `POST /sessoes`.
- Toda tool de negócio recebe `tool_context: ToolContext` e lê o apartamento de
  `tool_context.state["apartamento"]`. Nenhuma tool declara um parâmetro de apartamento.
- Tools de consulta de disponibilidade devolvem só `livre`/`ocupada`.
- Não existe tool que aceite "apartamento de outra pessoa" — logo não há caminho, nem por prompt
  injection, para ler ou alterar dados de outro apartamento.

## RAG do regulamento (Garantia 4)

- `regulamento/chunker.py`: fatia `dados/regulamento.md` em chunks por capítulo/artigo.
- `regulamento/index.py`: embeda os chunks (uma vez, cacheado), expõe `buscar(pergunta, k=2)`.
- Tool `consultar_regulamento(pergunta)` do especialista de regulamento devolve só os chunks
  relevantes.
- O agente principal não tem o regulamento nas instruções; só decide "isso é dúvida de
  regulamento, delega pro especialista".
- Nenhum evento de sessão deve conter o arquivo inteiro — só a pergunta, a tool call, o(s) chunk(s)
  retornado(s) e a resposta final.

## Exclusividade de reserva (Garantia 5)

- `db/condo_repo.criar_reserva` abre `BEGIN IMMEDIATE`, tenta `INSERT`, depende do índice único
  parcial `(area, data) WHERE status='ativa'` (ver ADR-04) pra falhar na segunda tentativa
  concorrente. Captura `IntegrityError` e devolve um resultado de domínio ("já ocupada"), nunca uma
  exceção não tratada — a tool e a API respondem normalmente (sem `500`).

## Mapeamento para o contrato HTTP

| Rota | Módulo responsável |
|---|---|
| `POST /sessoes` | `app/main.py` → cria sessão ADK, grava `apartamento` no state |
| `POST /sessoes/{id}/mensagens` | `app/main.py` → `adk_runtime.enviar_mensagem` |
| `POST /sessoes/{id}/confirmacoes` | `app/main.py` → `adk_runtime.responder_confirmacao` |
| `GET /sessoes/{id}/eventos` | `app/main.py` → lê eventos via `SqliteSessionService` |
| `GET /apartamentos/{n}/reservas` | `app/main.py` → `db/condo_repo.listar_reservas(apartamento)` |
| `GET /apartamentos/{n}/visitantes` | `app/main.py` → `db/condo_repo.listar_visitantes(apartamento)` |

As rotas de verificação **não** passam pelo Runner/modelo — leem `aurora_condo.db` direto.
