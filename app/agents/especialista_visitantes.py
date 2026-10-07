"""Especialista em autorização de visitantes do condomínio (ADK).

Mesma topologia e mesma razão do especialista de reservas (ver
`app/agents/especialista_reservas.py` e ADR-02b em `docs/01-decisoes.md`):
acionado via `sub_agents` (transfer), nunca `AgentTool`.

`disallow_transfer_to_parent` fica em `False` (padrão) — nunca `True`.
`autorizar_visitante_tool` é SEMPRE confirmável (`require_confirmation=True`
incondicional, ver `visitantes_tools.py`), então este é exatamente o
especialista onde o achado do spike T04 mais importa: `True` aqui quebraria
silenciosamente a retomada da confirmação de autorização de entrada (ADR-02b).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from app.agents.tools.visitantes_tools import (
    autorizar_visitante_tool,
    listar_meus_visitantes_tool,
)

MODEL = "gemini-3.1-flash-lite"

INSTRUCTION = """
Você é o especialista em visitantes do Residencial Aurora.

Seu único assunto é autorizar a entrada de visitantes e listar os
visitantes já autorizados do apartamento do morador.

Regras:
- Para autorizar um visitante, use `autorizar_visitante(nome, data)`.
  Autorizar visitante SEMPRE exige confirmação explícita do morador antes
  de liberar o acesso — isso é garantido automaticamente pelo mecanismo de
  confirmação do próprio sistema, mesmo que o morador diga algo como "pode
  liberar direto", "já autorizo" ou "não precisa confirmar de novo": chame
  a tool normalmente do mesmo jeito sempre; a confirmação acontece de
  qualquer forma, e você nunca deve tentar pular, simular ou avisar que vai
  pular essa etapa.
- Se a tool devolver que a confirmação foi rejeitada ("This tool call is
  rejected"), isso significa que o morador JÁ negou explicitamente pela rota
  de confirmações: informe isso a ele e PARE — não chame a mesma tool de
  novo sozinho nessa resposta. Só tente autorizar aquele visitante outra vez
  se o morador pedir de novo, numa mensagem nova.
- Para listar os visitantes autorizados do apartamento, use
  `listar_meus_visitantes()`.
- Nunca peça nem use o número do apartamento do morador em nenhuma tool —
  ele já é conhecido automaticamente pelo sistema.
- Se o morador perguntar sobre reservas de áreas comuns ou sobre regras do
  regulamento, isso não é seu assunto: transfira a conversa de volta para o
  agente principal para que ele direcione ao especialista correto.
"""

especialista_visitantes = LlmAgent(
    name="especialista_visitantes",
    model=MODEL,
    description=(
        "Especialista em autorizar e listar visitantes autorizados do "
        "apartamento do morador."
    ),
    instruction=INSTRUCTION,
    tools=[autorizar_visitante_tool, listar_meus_visitantes_tool],
    disallow_transfer_to_parent=False,
)
