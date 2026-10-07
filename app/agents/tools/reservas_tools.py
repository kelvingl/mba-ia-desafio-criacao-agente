"""Function tools de reservas para o especialista de reservas (ADK).

Contrato exato (assinatura vista pelo modelo) em
`docs/03-modelo-dados.md#tools-expostas-aos-agentes-assinatura-vista-pelo-modelo`.

ADR-03 (`docs/01-decisoes.md`): o apartamento nunca é parâmetro de tool — toda
função aqui que precisa dele lê `tool_context.state["apartamento"]`, nunca um
argumento preenchido pelo modelo. Isso é o que garante a Garantia 2 sem
depender do modelo "decidir direito".

Mecanismo de confirmação condicional (ADR-02/ADR-02b): `FunctionTool.__init__`
aceita `require_confirmation: bool | Callable[..., bool]` (ver código-fonte
instalado em `google/adk/tools/function_tool.py`). Usamos a forma *callable*
(`_requer_confirmacao_reserva`) em vez de um `bool` fixo, porque a exigência de
confirmação depende de um dado de negócio (taxa da área) só conhecido em tempo
de chamada, por chamada — um `bool` fixo marcaria a tool inteira como sempre
(ou nunca) confirmável, o que exigiria confirmação também para a quadra
(taxa=0), violando a regra de negócio. O ADK invoca esse callable com os
mesmos kwargs que seriam passados para a função real (`area`, `data`,
`tool_context` — ver `FunctionTool.run_async`), então a assinatura abaixo
espelha a de `reservar_area`.
"""

from __future__ import annotations

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.db import condo_repo


def consultar_disponibilidade(area: str, data: str) -> str:
    """Consulta se `area` está livre em `data`.

    Nunca recebe nem devolve apartamento/código de quem reservou (ADR-03) —
    só a disponibilidade em si.

    Args:
        area: id da área (ex.: "salao-de-festas").
        data: data no formato AAAA-MM-DD.

    Returns:
        "livre" ou "ocupada".
    """
    livre = condo_repo.consultar_disponibilidade(area, data)
    return "livre" if livre else "ocupada"


def _requer_confirmacao_reserva(
    area: str, data: str, tool_context: ToolContext
) -> bool:
    """Callable de `require_confirmation` de `reservar_area`.

    Só exige confirmação quando a área tem taxa > 0 (regra de negócio: áreas
    gratuitas, ex. "quadra" no seed, reservam direto). `data` e `tool_context`
    não influenciam a decisão, mas precisam estar na assinatura porque o ADK
    invoca este callable com os mesmos kwargs de `reservar_area`.
    """
    info_area = condo_repo.obter_area(area)
    taxa = info_area["taxa"] if info_area else 0
    return taxa > 0


def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cria uma reserva de área comum para o apartamento da sessão atual.

    O apartamento nunca é um argumento do modelo (ADR-03): é lido de
    `tool_context.state["apartamento"]`, gravado uma única vez na criação da
    sessão. Se a área tiver taxa > 0, o ADK pausa esta tool pedindo
    confirmação antes de executar (ver `_requer_confirmacao_reserva` acima).

    Args:
        area: id da área (ex.: "salao-de-festas").
        data: data no formato AAAA-MM-DD.
        tool_context: injetado pelo ADK — não é visto pelo modelo.

    Returns:
        {"ok": True, "codigo": str} ou {"ok": False, "motivo": "ocupada"}.
    """
    apartamento = tool_context.state["apartamento"]
    # `obter_area` só é consultado aqui para documentar/logar a taxa que
    # disparou (ou não) a confirmação; quem de fato decide se confirma é
    # `_requer_confirmacao_reserva`, chamado pelo FunctionTool antes de
    # chegar nesta função.
    condo_repo.obter_area(area)
    return condo_repo.criar_reserva(apartamento, area, data)


# Registrada com `require_confirmation` *callable* (não bool fixo) — ver
# docstring do módulo e de `_requer_confirmacao_reserva`.
reservar_area_tool = FunctionTool(
    reservar_area, require_confirmation=_requer_confirmacao_reserva
)


def cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do apartamento da sessão atual.

    Sem confirmação (regra de negócio 4: morador cancela as próprias reservas
    sem confirmação). O apartamento usado é sempre o da sessão
    (`tool_context.state["apartamento"]`), nunca um texto do usuário — mesmo
    que o `codigo` informado pertença a outro apartamento,
    `condo_repo.cancelar_reserva` só cancela se o apartamento bater (defesa em
    profundidade), então nada é cancelado nesse caso.

    Args:
        codigo: código da reserva (ex.: "RSV-1").
        tool_context: injetado pelo ADK — não é visto pelo modelo.

    Returns:
        {"ok": True} ou {"ok": False, "motivo": "nao_encontrada"}.
    """
    apartamento = tool_context.state["apartamento"]
    return condo_repo.cancelar_reserva(apartamento, codigo)


cancelar_reserva_tool = FunctionTool(cancelar_reserva)


def listar_minhas_reservas(tool_context: ToolContext) -> list[dict]:
    """Lista as reservas ativas do apartamento da sessão atual.

    Args:
        tool_context: injetado pelo ADK — não é visto pelo modelo.

    Returns:
        [{"codigo": str, "area": str, "data": str}, ...].
    """
    apartamento = tool_context.state["apartamento"]
    return condo_repo.listar_reservas(apartamento)


listar_minhas_reservas_tool = FunctionTool(listar_minhas_reservas)
