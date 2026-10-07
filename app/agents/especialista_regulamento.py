"""Especialista em consultas ao regulamento do condomínio (ADK).

`disallow_transfer_to_parent=True` aqui — ao contrário dos outros dois
especialistas, e escolha deliberada documentada em T08 (não copiada de
nenhum padrão anterior):

`consultar_regulamento` nunca é confirmável (não tem `require_confirmation`
em `regulamento_tools.py`), então este especialista está fora do risco
provado em ADR-02b (`docs/01-decisoes.md`) — aquele achado só importa para
retomar uma confirmação pendente no especialista certo depois de um
restart, e isso nunca acontece aqui.

Sem esse risco, a escolha de `disallow_transfer_to_parent` passa a ser só
"qual config deixa o roteamento mais confiável quando o assunto muda de
turno para turno?". `Runner._find_agent_to_run` (google/adk/runners.py)
reaproveita o último agente que respondeu, em todo novo turno, desde que
ele seja "transferível até a raiz" — com `True`, este especialista deixa de
ser aceito nessa checagem, e todo novo turno cai direto no fallback para o
`root_agent`, que então decide pelas próprias instruções de roteamento se o
novo assunto continua sendo regulamento ou deve ir para outro especialista.
Isso evita depender do LLM deste especialista "lembrar" de chamar
`transfer_to_agent` de volta quando o assunto muda — ele não tem tools de
reserva/visitante pra responder nada fora do regulamento, então o custo de
ele tentar responder (ou inventar) em vez de transferir seria mais alto
aqui do que nos outros dois especialistas (que têm instrução explícita e
motivo de negócio — confirmação pendente — pra manter `False`). Como esta
tool nunca pede confirmação, `True` não tem nenhum efeito colateral sobre
R1/ADR-02b.

Instruções: SEMPRE usar `consultar_regulamento` antes de responder qualquer
dúvida sobre regras do condomínio — nunca responder de memória própria
(Garantia 4).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from app.agents.tools.regulamento_tools import consultar_regulamento

MODEL = "gemini-3.1-flash-lite"

INSTRUCTION = """
Você é o especialista em regulamento do Residencial Aurora.

Seu único assunto é responder dúvidas sobre as regras do condomínio
(regulamento interno).

Regra absoluta: para QUALQUER pergunta sobre o regulamento, SEMPRE chame a
tool `consultar_regulamento(pergunta)` antes de responder, e baseie sua
resposta só nos trechos que ela devolver. Nunca responda uma dúvida de
regulamento de memória própria, mesmo que pareça óbvio ou que você "ache
que sabe a resposta" — você não tem o texto do regulamento memorizado de
forma confiável, só a tool tem. Se a tool não encontrar nada relevante,
diga ao morador que não encontrou essa informação no regulamento; não
invente uma resposta.

Se o morador perguntar sobre reservar área comum ou autorizar visitante,
isso não é seu assunto.
"""

especialista_regulamento = LlmAgent(
    name="especialista_regulamento",
    model=MODEL,
    description=(
        "Especialista em responder dúvidas sobre o regulamento interno do "
        "condomínio, sempre consultando a base de regras antes de "
        "responder."
    ),
    instruction=INSTRUCTION,
    tools=[consultar_regulamento],
    disallow_transfer_to_parent=True,
)
