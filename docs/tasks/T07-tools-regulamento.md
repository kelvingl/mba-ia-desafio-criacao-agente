# T07 — Tool de consulta ao regulamento

**Depende de**: T03. **Bloqueia**: T08.

## Objetivo

Expor a busca do RAG (`T03`) como uma tool de agente, mantendo a Garantia 4 (nenhum trecho de
capítulo não relacionado entra nos eventos da sessão).

## Passos

1. `app/agents/tools/regulamento_tools.py`:
   - `consultar_regulamento(pergunta: str) -> str` — chama `regulamento.index.buscar(pergunta)`,
     concatena os chunks retornados num texto curto, devolve.
2. Sem `tool_context` necessário aqui (não depende do apartamento — regulamento é igual pra todo
   mundo).
3. Garantir que a função não tem fallback que leia o arquivo inteiro em caso de busca vazia (se o
   índice não achar nada relevante, devolver uma string indicando isso, não o documento completo).

## Entregáveis

- `app/agents/tools/regulamento_tools.py`.

## Critério de aceite

- Chamar a tool com a pergunta do passo 12 do fluxo do avaliador (piscina domingo) devolve texto
  que contém o horário de fechamento certo.
- O retorno da tool nunca excede alguns parágrafos (sinal de que não virou "arquivo inteiro"
  disfarçado de resposta de tool).
