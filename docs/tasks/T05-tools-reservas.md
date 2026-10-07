# T05 — Tools de reservas

**Depende de**: T02. **Bloqueia**: T08.

## Objetivo

Expor `app/db/condo_repo.py` como function tools do ADK para o especialista de reservas, seguindo
a assinatura "vista pelo modelo" definida em
[`../03-modelo-dados.md`](../03-modelo-dados.md#tools-expostas-aos-agentes-assinatura-vista-pelo-modelo).

## Passos

1. `app/agents/tools/reservas_tools.py` com:
   - `consultar_disponibilidade(area: str, data: str) -> str` — chama
     `condo_repo.consultar_disponibilidade`, devolve `"livre"`/`"ocupada"` (string simples, sem
     apartamento/código).
   - `reservar_area(area: str, data: str, tool_context: ToolContext) -> dict` — lê
     `apartamento = tool_context.state["apartamento"]` (nunca um parâmetro do modelo), consulta
     `obter_area` pra saber a taxa; se `taxa > 0`, marcar a tool pra exigir confirmação (mecanismo
     decidido em `T04`); chama `condo_repo.criar_reserva`.
   - `cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict` — lê apartamento da
     sessão, chama `condo_repo.cancelar_reserva(apartamento, codigo)`. Sem confirmação (regra de
     negócio 4: morador cancela as próprias reservas sem confirmação).
   - `listar_minhas_reservas(tool_context: ToolContext) -> list[dict]` — lê apartamento da sessão,
     chama `condo_repo.listar_reservas`.
2. Garantir que **nenhuma** destas funções tem parâmetro `apartamento`/`numero` no schema que o
   ADK gera para o modelo — só `tool_context` (que o ADK injeta, não o modelo).
3. Decidir e aplicar a forma de marcar `reservar_area` como "exige confirmação" conforme o que o
   spike `T04` validou.

## Entregáveis

- `app/agents/tools/reservas_tools.py`.

## Critério de aceite

- Inspecionar o schema de tool gerado (ex.: imprimir a declaration da function tool) e confirmar
  que não há campo de apartamento.
- Chamar `reservar_area` para uma área com taxa > 0 pausa esperando confirmação; para a quadra
  (taxa 0) executa direto.
- `cancelar_reserva` com um código de outro apartamento (passado deliberadamente num teste) não
  cancela nada — `condo_repo.cancelar_reserva` já valida isso, mas confirmar aqui que o
  `apartamento` passado é sempre o da sessão, nunca um texto do usuário.
