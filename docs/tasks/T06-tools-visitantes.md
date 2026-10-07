# T06 — Tools de visitantes

**Depende de**: T02. **Bloqueia**: T08.

## Objetivo

Expor as operações de visitantes como function tools do ADK para o especialista de visitantes,
seguindo o contrato em
[`../03-modelo-dados.md`](../03-modelo-dados.md#tools-expostas-aos-agentes-assinatura-vista-pelo-modelo).

## Passos

1. `app/agents/tools/visitantes_tools.py` com:
   - `autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict` — lê
     `apartamento` do `tool_context.state`, chama `condo_repo.autorizar_visitante`. **Sempre**
     exige confirmação (regra de negócio 3: autorizar visitante libera acesso — Garantia 1 cobre
     qualquer ação que libere acesso, sem exceção, mesmo que o morador diga "já confirmei").
   - `listar_meus_visitantes(tool_context: ToolContext) -> list[dict]` — lê apartamento da sessão,
     chama `condo_repo.listar_visitantes`.
2. Nenhuma das duas tem parâmetro de apartamento no schema visto pelo modelo.
3. Aplicar o mesmo mecanismo de "exige confirmação" validado em `T04`.

## Entregáveis

- `app/agents/tools/visitantes_tools.py`.

## Critério de aceite

- `autorizar_visitante` sempre pausa esperando confirmação, mesmo que a mensagem do usuário diga
  "pode liberar direto, eu confirmo por aqui" (esse texto não deve ter nenhum efeito sobre o fato
  de a tool pausar — é o teste do passo 11 do fluxo do avaliador).
- Antes da aprovação, `GET /apartamentos/{n}/visitantes` não lista o novo visitante; depois da
  aprovação, lista.
