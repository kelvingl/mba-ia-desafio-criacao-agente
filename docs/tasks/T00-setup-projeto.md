# T00 — Setup do projeto

**Depende de**: nada. **Bloqueia**: T01–T04.

## Objetivo

Deixar o repositório com projeto Python instalável via `uv`, pronto para as demais tarefas
escreverem código dentro de `app/`.

## Passos

1. `uv init --python 3.12` (ou garantir `pyproject.toml` com `requires-python = ">=3.12"`).
2. Adicionar dependências: `google-adk` (fixar `==2.2.0` por ora — pode subir depois do spike T04
   confirmar compatibilidade, ver ADR-06/R6 em `../05-riscos.md`), `fastapi`, `uvicorn[standard]`,
   `python-dotenv`, `google-genai` (embeddings do regulamento).
3. Criar `.env.example` com, no mínimo:
   ```
   GOOGLE_API_KEY=
   ```
   (adicionar outras variáveis conforme forem necessárias nas tarefas seguintes — este arquivo é
   vivo, cada tarefa que introduzir uma env var atualiza aqui).
4. Confirmar que `.env` já está no `.gitignore` (está).
5. Criar esqueleto de pastas vazio com `__init__.py` onde fizer sentido:
   ```
   app/{agents/tools,db,regulamento,scripts}
   data/            # aurora_sessions.db e aurora_condo.db nascem aqui, .gitignore'd
   ```
6. Adicionar `data/` ao `.gitignore` (bancos SQLite não são versionados).

## Entregáveis

- `pyproject.toml`, `uv.lock` versionados.
- `.env.example` versionado, `.env` ignorado.
- `uv sync` funciona sem erro num clone limpo.

## Critério de aceite

- `uv run python -c "import google.adk, fastapi"` não falha.
- `uv.lock` commitado reflete exatamente a versão do ADK escolhida.
