"""Tools de visitantes expostas ao especialista de visitantes (ADK).

Contrato exato em `docs/03-modelo-dados.md` (seção "Tools expostas aos
agentes"). Nenhuma das duas funções abaixo recebe `apartamento` como
parâmetro visto pelo modelo (ADR-03 em `docs/01-decisoes.md`) — ele é lido de
`tool_context.state["apartamento"]`, gravado uma única vez por `POST
/sessoes`.

`autorizar_visitante` libera acesso ao condomínio (regra de negócio 3), então
é registrada com `require_confirmation=True` incondicional (sem callable, sem
`if`) — a Garantia 1 não abre exceção pra esse caso, mesmo que o texto do
morador diga algo como "pode liberar direto, eu confirmo por aqui": isso é
conteúdo de mensagem, não afeta o mecanismo nativo de confirmação do ADK
(mesmo mecanismo validado no spike de T04 — ver ADR-02/ADR-02b). Note a
diferença com `reservar_area` (T05): lá a confirmação é condicional à taxa da
área: aqui é sempre.
"""

from __future__ import annotations

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.db import condo_repo


def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no apartamento da sessão atual.

    Libera acesso físico ao condomínio — sempre exige confirmação explícita
    do morador antes de executar (ver `require_confirmation=True` na
    `FunctionTool` abaixo). `apartamento` nunca é parâmetro: vem de
    `tool_context.state["apartamento"]`.

    Args:
        nome: Nome do visitante a autorizar.
        data: Data da visita, formato AAAA-MM-DD.

    Returns:
        {"ok": True} em caso de sucesso.
    """
    apartamento = tool_context.state["apartamento"]
    return condo_repo.autorizar_visitante(apartamento, nome, data)


def listar_meus_visitantes(tool_context: ToolContext) -> list[dict]:
    """Lista os visitantes autorizados para o apartamento da sessão atual.

    `apartamento` nunca é parâmetro: vem de `tool_context.state["apartamento"]`.

    Returns:
        Lista de {"nome": str, "data": str}.
    """
    apartamento = tool_context.state["apartamento"]
    return condo_repo.listar_visitantes(apartamento)


# `require_confirmation=True` sem condição: ao contrário de `reservar_area`
# (T05, condicional a `taxa > 0`), aqui não existe caminho de execução direta
# — regra de negócio 3 + Garantia 1.
autorizar_visitante_tool = FunctionTool(autorizar_visitante, require_confirmation=True)
listar_meus_visitantes_tool = FunctionTool(listar_meus_visitantes)
