# T10 — Rotas FastAPI completas

**Depende de**: T02, T09. **Bloqueia**: T11.

## Objetivo

Implementar `app/main.py` com as 6 rotas do contrato, exatamente como especificado no
`ENUNCIADO.md` (seção "Contrato da API").

## Passos

1. `POST /sessoes` — body `{"apartamento": str}`, chama `adk_runtime.criar_sessao`, devolve `201`
   `{"session_id": str}`.
2. `POST /sessoes/{session_id}/mensagens` — body `{"texto": str}`; se sessão não existe, `404`;
   senão chama `adk_runtime.enviar_mensagem`, devolve `200` no formato do contrato.
3. `POST /sessoes/{session_id}/confirmacoes` — body `{"id": str, "confirmado": bool}`; se sessão
   não existe, `404`; senão chama `adk_runtime.responder_confirmacao` — `None` → `409`; senão
   `200` no mesmo formato da rota de mensagens.
4. `GET /sessoes/{session_id}/eventos` — `404` se sessão não existe; senão `200` com a lista
   completa de eventos.
5. `GET /apartamentos/{numero}/reservas` — `200` com `[{"codigo", "area", "data"}]` via
   `condo_repo.listar_reservas` (sem passar pelo Runner).
6. `GET /apartamentos/{numero}/visitantes` — `200` com `[{"nome", "data"}]` via
   `condo_repo.listar_visitantes`.
7. Inicialização da app: construir o índice do regulamento (`T03`) se ainda não houver cache,
   abrir conexões de banco — tudo no lifespan/startup do FastAPI, não a cada request.

## Entregáveis

- `app/main.py`.
- Comando de subida documentado (provavelmente `uv run uvicorn app.main:app --port 8000`).

## Critério de aceite

- Todas as respostas de erro/sucesso batem com os códigos HTTP do contrato (`201`, `200`, `404`,
  `409`) nos casos descritos no `ENUNCIADO.md`.
- `uv run uvicorn app.main:app --port 8000` sobe e responde em `http://localhost:8000`.
- Rodar manualmente os passos 1–2 do fluxo do avaliador (criar sessão, checar reservas/visitantes
  iniciais do 101/302) passa antes de prosseguir pra `T11`.
