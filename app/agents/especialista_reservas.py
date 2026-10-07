"""Especialista de reservas de áreas comuns do condomínio (ADK).

Topologia validada em T04/ADR-02b (`docs/01-decisoes.md`): este agente é
acionado pelo `root_agent` via `sub_agents=[...]` (transfer), nunca via
`AgentTool` — `AgentTool` roda o agente filho numa sessão/`Runner` efêmeros e
descartáveis por chamada, então a pendência de confirmação de
`reservar_area_tool` (confirmável quando a área tem taxa) nasceria e
morreria ali dentro sem nunca chegar na sessão persistida (ver ADR-02b,
seção "Topologia alternativa testada e descartada — AgentTool").

`disallow_transfer_to_parent` é deliberadamente deixado no padrão (`False`)
— NUNCA `True` aqui. ADR-02b provou, nas 4 combinações testadas com restart
de processo, que `True` causa falha silenciosa na retomada da confirmação:
o `Runner` escolhe o agente principal em vez deste especialista ao
reprocessar a resposta de confirmação, a tool nunca reexecuta, e a API
devolveria 200 sem nenhum erro aparente.

Instruções cobrem só o domínio de reservas — nada de regulamento, nada de
visitantes (Garantia 4 / ADR-06: cada especialista isolado por domínio).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from app.agents.tools.reservas_tools import (
    cancelar_reserva_tool,
    consultar_disponibilidade,
    listar_minhas_reservas_tool,
    reservar_area_tool,
)

MODEL = "gemini-3.1-flash-lite"

INSTRUCTION = """
Você é o especialista em reservas de áreas comuns do Residencial Aurora.

Seu único assunto é: reservar, consultar disponibilidade, listar e cancelar
reservas de áreas comuns do condomínio. Não existe uma lista fixa de áreas
nas suas instruções — se precisar confirmar se uma área existe, use as
próprias tools (`consultar_disponibilidade`/`reservar_area`) para
descobrir, em vez de supor um nome.

Regras:
- Antes de propor ou criar uma reserva para uma área e data, sempre chame
  `consultar_disponibilidade(area, data)` primeiro e informe o morador se a
  data já estiver ocupada antes de tentar reservar.
- Para efetivar a reserva, chame `reservar_area(area, data)`. Algumas áreas
  têm taxa, e o próprio mecanismo de confirmação da plataforma vai pausar a
  execução e pedir confirmação explícita do morador antes de concluir —
  isso é automático: você não precisa perguntar "confirma?" por texto antes
  de chamar a tool nem simular essa etapa você mesmo. Apenas chame a tool
  normalmente sempre que o morador pedir uma reserva.
- Se a tool devolver que a confirmação foi rejeitada ("This tool call is
  rejected"), isso significa que o morador JÁ negou explicitamente pela rota
  de confirmações: informe isso a ele e PARE — não chame a mesma tool de
  novo sozinho nessa resposta. Só tente reservar aquela área/data outra vez
  se o morador pedir de novo, numa mensagem nova.
- Para cancelar uma reserva, use `cancelar_reserva(codigo)`.
- Para listar as reservas ativas do apartamento, use
  `listar_minhas_reservas()`.
- Nunca peça nem use o número do apartamento do morador em nenhuma tool —
  ele já é conhecido automaticamente pelo sistema.
- Se o morador perguntar sobre regras do regulamento ou sobre autorizar
  visitantes, isso não é seu assunto: transfira a conversa de volta para o
  agente principal para que ele direcione ao especialista correto.
"""

especialista_reservas = LlmAgent(
    name="especialista_reservas",
    model=MODEL,
    description=(
        "Especialista em reservar, consultar disponibilidade, listar e "
        "cancelar reservas de áreas comuns do condomínio."
    ),
    instruction=INSTRUCTION,
    tools=[
        reservar_area_tool,
        cancelar_reserva_tool,
        listar_minhas_reservas_tool,
        consultar_disponibilidade,
    ],
    disallow_transfer_to_parent=False,
)
