# T09 — Runner/App + fluxo HTTP de confirmação

**Depende de**: T04, T08. **Bloqueia**: T10.

## Objetivo

Montar `app/adk_runtime.py`: o `Runner`/`App` com `SqliteSessionService` (SQLite), e as duas
funções que a API vai chamar — enviar mensagem e responder confirmação — incluindo a integração
com a tabela `confirmacoes` de `aurora_condo.db` (ver ADR-02).

## Passos

1. Configurar `SqliteSessionService` apontando pra `data/aurora_sessions.db`, com a
   configuração de `App`/Runner que `T04` validou (resume, bloqueios de transferência, etc.).
2. `criar_sessao(apartamento: str) -> str`: cria sessão ADK, grava
   `session.state["apartamento"] = apartamento` na criação, devolve `session_id`.
3. `enviar_mensagem(session_id: str, texto: str) -> dict`:
   - Roda o turno via Runner.
   - Se o turno parar numa confirmação pendente de tool: extrai os argumentos reais da chamada
     (área/data ou nome/data) do evento, chama `condo_repo.criar_confirmacao(session_id, acao,
     detalhes)`, devolve `{"resposta": "", "confirmacoes_pendentes": [...]}`.
   - Se terminar normalmente: devolve `{"resposta": texto_final, "confirmacoes_pendentes":
     condo_repo.listar_confirmacoes_pendentes(session_id)}` (deveria ser `[]` neste caso, mas
     recalcular do banco em vez de assumir é mais seguro).
4. `responder_confirmacao(session_id: str, confirmacao_id: str, confirmado: bool) -> dict | None`:
   - `condo_repo.responder_confirmacao(...)` — se devolver `ok=False`, a função retorna `None`
     (API traduz pra `409`).
   - Se `ok=True` e `confirmado=True`: injeta a resposta de confirmação no Runner usando o
     mecanismo validado em `T04`, deixa a tool pausada retomar, captura o resultado final (mesma
     lógica de extração de `enviar_mensagem`).
   - Se `ok=True` e `confirmado=False`: não toca no Runner pra executar nada; devolve resposta no
     mesmo formato com `resposta` descrevendo que a ação foi cancelada (texto livre) e
     `confirmacoes_pendentes` recalculado.
5. `listar_eventos(session_id: str) -> list[dict] | None`: lê os eventos da sessão via
   `SqliteSessionService`; `None` se a sessão não existir (API traduz pra `404`).

## Entregáveis

- `app/adk_runtime.py` com as 5 funções acima.

## Critério de aceite

- Repetir o teste de restart do `T04`/`T08` agora passando pela função `responder_confirmacao`
  (não pelo script de spike).
- Reenviar a mesma confirmação já respondida: `condo_repo.responder_confirmacao` devolve
  `ok=False` na segunda vez (porque o status já não é `pending`), sem tocar no Runner.
- `enviar_mensagem` nunca lança excção pra fora em caminhos de negócio esperados (área ocupada,
  etc.) — erros de negócio voltam como resposta de conversa normal, não como `500`.
