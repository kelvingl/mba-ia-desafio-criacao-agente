"""Agente principal do assistente do Residencial Aurora (ADK).

Topologia validada no spike T04 (ADR-02b, `docs/01-decisoes.md`): os 3
especialistas são acionados via `sub_agents=[...]` (transfer), NUNCA via
`AgentTool` — `AgentTool` roda o agente filho numa sessão/`Runner` efêmeros
e descartáveis por chamada, o que faz qualquer pendência de confirmação
nascer e morrer ali dentro sem sobreviver na sessão persistida (ver
ADR-02b, "Topologia alternativa testada e descartada — AgentTool").

Este agente NÃO declara nenhuma tool de negócio (reservar, cancelar,
autorizar, consultar regulamento) — só decide, pelo assunto da mensagem,
para qual dos 3 especialistas transferir a conversa (ADR-06). As instruções
abaixo descrevem OS ESPECIALISTAS e o CRITÉRIO de roteamento por assunto —
nunca o conteúdo do regulamento em si (Garantia 4: nenhum trecho de
`dados/regulamento.md` pode aparecer aqui, nem resumido nem copiado; quem
conhece o conteúdo do regulamento é só `especialista_regulamento`, e mesmo
ele só através da tool `consultar_regulamento` — o agente principal nunca
carrega esse conteúdo).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from app.agents.especialista_regulamento import especialista_regulamento
from app.agents.especialista_reservas import especialista_reservas
from app.agents.especialista_visitantes import especialista_visitantes

MODEL = "gemini-3.1-flash-lite"

INSTRUCTION = """
Você é o assistente virtual do Residencial Aurora e atende moradores cujo
apartamento já está identificado pela sessão.

Você mesmo NUNCA executa reservas, cancelamentos, autorizações de
visitante nem busca no regulamento — você só decide para qual dos 3
especialistas abaixo transferir a conversa, de acordo com o assunto da
mensagem do morador, e transfere imediatamente (sem tentar responder o
assunto de domínio você mesmo):

- `especialista_reservas`: qualquer assunto sobre reservar, consultar
  disponibilidade, listar ou cancelar reserva de área comum do condomínio
  (ex.: salão de festas, churrasqueira, quadra, ou qualquer outra área
  comum).
- `especialista_visitantes`: qualquer assunto sobre autorizar a entrada de
  um visitante ou listar visitantes já autorizados.
- `especialista_regulamento`: qualquer dúvida sobre regras, normas ou
  regulamento interno do condomínio (ex.: horários de uso de áreas comuns,
  regras de convivência, barulho, animais, etc.). Você não conhece o
  conteúdo do regulamento — só o `especialista_regulamento` sabe consultá-lo.

Se a mensagem misturar mais de um assunto, trate primeiro o que vier
primeiro e deixe claro ao morador que ele pode pedir o restante a seguir.
Se não tiver certeza de qual especialista é o certo, pergunte ao morador
antes de transferir.
"""

root_agent = LlmAgent(
    name="agente_principal",
    model=MODEL,
    description="Agente principal do assistente do Residencial Aurora.",
    instruction=INSTRUCTION,
    sub_agents=[
        especialista_reservas,
        especialista_visitantes,
        especialista_regulamento,
    ],
)
