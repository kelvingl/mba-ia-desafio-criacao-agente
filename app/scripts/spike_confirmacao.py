"""Spike T04 — confirmação nativa de tool do ADK + sessão persistida + restart.

OBJETIVO (ver docs/tasks/T04-spike-confirmacao.md e docs/05-riscos.md R1):
provar, lendo o código-fonte instalado do google-adk==2.2.0 e executando contra
ele, que "tool pede confirmação -> processo morre -> processo novo -> cliente
responde -> tool executa" funciona com sessão SQLite persistida, e descobrir
exatamente qual topologia/config garante isso.

Este script NÃO faz chamadas reais ao Gemini: usa um `BaseLlm` fake
("ScriptedLlm") que decide a próxima resposta olhando o conteúdo da requisição,
sem rede nem GOOGLE_API_KEY. Isso é deliberado -- o pedaço que depende do
modelo de verdade é só "o LLM decide chamar a tool", que não é o que está em
risco aqui (R1 é sobre o Runner/ADK escolher o agente certo pra retomada, uma
lógica 100% determinística dentro do framework, independente do modelo). Com
isso dá pra validar o mecanismo real do ADK (branch, resumability_config,
find_agent_to_run, SqliteSessionService em disco) com precisão total e sem
gastar chamada de API.

Cada subcomando abaixo é pensado para ser executado como um processo `uv run
python` SEPARADO (northing in-memory é compartilhado entre eles -- só o
arquivo sqlite em disco e um pequeno JSON de "handoff" com o id da function
call pendente). Isso É o teste de restart pedido pelo passo 3 da task: não há
estado de processo sobrevivendo entre as chamadas, só o que está no .db.

Subcomandos:
  success_phase1   sub_agents + App.resumability_config.is_resumable=True.
                    Cria sessão, manda "reservar", o especialista pede
                    confirmação pra tool com taxa, processo termina.
  success_phase2   processo NOVO: carrega a mesma sessão do mesmo sqlite,
                    responde a confirmação, confirma que a tool reexecutou e
                    que a resposta voltou do especialista (não do principal).
  fail_phase1       mesma topologia, mas SEM resumability_config e com
                    disallow_transfer_to_parent=True no especialista (combo
                    plausível de alguém escolher por "boas práticas").
  fail_phase2       processo novo: responde a confirmação, mostra a falha
                    SILENCIOSA -- sem exceção, mas a tool nunca reexecuta.
  agenttool_demo    especialista acionado via AgentTool em vez de sub_agents.
                    Um único processo já basta: mostra que a pendência de
                    confirmação nem chega a sobreviver ao retorno da tool pai,
                    então nem adianta testar restart nessa topologia.

Uso:
  uv run python app/scripts/spike_confirmacao.py success_phase1
  uv run python app/scripts/spike_confirmacao.py success_phase2
  uv run python app/scripts/spike_confirmacao.py fail_phase1
  uv run python app/scripts/spike_confirmacao.py fail_phase2
  uv run python app/scripts/spike_confirmacao.py agenttool_demo
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

SCRATCH_DIR = Path(
    "/tmp/claude-1000/-home-osboxes-repos-mba-ia-desafio-criacao-agente/"
    "06012183-0831-4766-8622-0fbf495c60fe/scratchpad/t04_spike"
)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

TOOL_NAME = "criar_reserva"
SPECIALIST_NAME = "especialista_reservas"
ROOT_NAME = "agente_principal"


def _get_function_response(content: Optional[types.Content], name: str):
    if not content or not content.parts:
        return None
    for part in content.parts:
        fr = part.function_response
        if fr and fr.name == name:
            return fr
    return None


def _has_function_call(content: Optional[types.Content], name: str) -> bool:
    if not content or not content.parts:
        return False
    return any(
        p.function_call and p.function_call.name == name for p in content.parts
    )


class ScriptedLlm(BaseLlm):
    """BaseLlm falso: decide a resposta olhando o llm_request, sem rede.

    `role` seleciona o roteiro: 'root' sempre transfere pro especialista;
    'specialist' chama a tool confirmável na primeira vez que vê uma mensagem
    de usuário sem function_response de `criar_reserva` no histórico, e
    responde com texto final quando já vê o resultado da tool.
    """

    role: str = "root"

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        contents = llm_request.contents

        if self.role == "root":
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="transfer_to_agent",
                                args={"agent_name": SPECIALIST_NAME},
                            )
                        )
                    ],
                )
            )
            return

        # role == "specialist". Só conta como "ja executou" a resposta de
        # SUCESSO da tool -- a resposta de erro "precisa confirmar" nao conta,
        # senao o script responderia texto final sem nunca pedir confirmacao.
        already_executed = any(
            (fr := _get_function_response(c, TOOL_NAME)) and fr.response.get("status") == "ok"
            for c in contents
        )
        if already_executed:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "Reserva do salao de festas confirmada para"
                                " 2030-04-20."
                            )
                        )
                    ],
                )
            )
            return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=TOOL_NAME,
                            args={"area": "salao-de-festas", "data": "2030-04-20"},
                        )
                    )
                ],
            )
        )


def criar_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cria uma reserva para a area e data informadas (gera cobranca)."""
    execucoes = tool_context.state.get("execucoes", 0) + 1
    tool_context.state["execucoes"] = execucoes
    return {
        "status": "ok",
        "codigo": f"RSV-SPIKE-{execucoes}",
        "area": area,
        "data": data,
    }


def build_agents(
    *, resumable: bool, disallow_transfer_to_parent: bool, via_agent_tool: bool
):
    tool = FunctionTool(criar_reserva, require_confirmation=True)

    specialist = LlmAgent(
        name=SPECIALIST_NAME,
        model=ScriptedLlm(model="scripted-specialist", role="specialist"),
        description="Cria reservas de areas comuns.",
        instruction="Crie a reserva pedida usando a tool disponivel.",
        tools=[tool],
        disallow_transfer_to_parent=disallow_transfer_to_parent,
    )

    if via_agent_tool:
        root = LlmAgent(
            name=ROOT_NAME,
            model=ScriptedLlm(model="scripted-root", role="root"),
            instruction="Delegue pedidos de reserva ao especialista.",
            tools=[AgentTool(agent=specialist)],
        )
        # ScriptedLlm do root precisa chamar a tool pelo NOME dela quando é
        # AgentTool -- o nome da function é o nome do agente (ver AgentTool).
        # Reaproveitamos o mesmo roteiro "transfer_to_agent" não serve aqui;
        # criamos uma variante dedicada abaixo.
        root.model = _AgentToolRootLlm(model="scripted-root-tool")
    else:
        root = LlmAgent(
            name=ROOT_NAME,
            model=ScriptedLlm(model="scripted-root", role="root"),
            instruction="Delegue pedidos de reserva ao especialista.",
            sub_agents=[specialist],
        )

    resumability_config = ResumabilityConfig(is_resumable=True) if resumable else None
    app = App(name="aurora_spike", root_agent=root, resumability_config=resumability_config)
    return app, specialist, tool


class _AgentToolRootLlm(BaseLlm):
    async def generate_content_async(self, llm_request, stream: bool = False):
        already_called = any(
            _get_function_response(c, SPECIALIST_NAME) for c in llm_request.contents
        )
        if already_called:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Encaminhado ao especialista.")],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=SPECIALIST_NAME,
                            args={"request": "Reserve o salao para 2030-04-20"},
                        )
                    )
                ],
            )
        )


def db_path(label: str) -> str:
    return str(SCRATCH_DIR / f"{label}.db")


def handoff_path(label: str) -> Path:
    return SCRATCH_DIR / f"{label}.handoff.json"


async def _run_phase1(label: str, *, resumable: bool, disallow_transfer: bool):
    app, specialist, _tool = build_agents(
        resumable=resumable,
        disallow_transfer_to_parent=disallow_transfer,
        via_agent_tool=False,
    )
    session_service = SqliteSessionService(db_path=db_path(label))
    runner = Runner(app=app, session_service=session_service)

    session = await session_service.create_session(
        app_name=app.name, user_id="apto-101"
    )
    print(f"[{label} phase1] session_id={session.id}")

    new_message = types.Content(
        role="user",
        parts=[types.Part(text="Reserve o salao de festas para 2030-04-20")],
    )
    events = []
    async for event in runner.run_async(
        user_id="apto-101", session_id=session.id, new_message=new_message
    ):
        events.append(event)
        print(
            f"[{label} phase1] event author={event.author!r} "
            f"long_running_tool_ids={event.long_running_tool_ids!r} "
            f"content={event.content!r}"
        )

    reloaded = await session_service.get_session(
        app_name=app.name, user_id="apto-101", session_id=session.id
    )
    fc_id = None
    fc_author = None
    for ev in reloaded.events:
        if ev.long_running_tool_ids:
            fc_id = next(iter(ev.long_running_tool_ids))
            fc_author = ev.author
            break

    if fc_id is None:
        print(f"[{label} phase1] ERRO: nenhum long_running_tool_ids encontrado")
        return

    handoff_path(label).write_text(
        json.dumps(
            {
                "session_id": session.id,
                "fc_id": fc_id,
                "fc_author": fc_author,
                "user_id": "apto-101",
            }
        )
    )
    print(
        f"[{label} phase1] pendencia capturada: fc_id={fc_id} "
        f"autor_do_pedido_de_confirmacao={fc_author} "
        f"(agora mate o processo e rode {label}_phase2 em um `uv run` novo)"
    )


async def _run_phase2(label: str, *, resumable: bool, disallow_transfer: bool):
    handoff = json.loads(handoff_path(label).read_text())
    app, specialist, _tool = build_agents(
        resumable=resumable,
        disallow_transfer_to_parent=disallow_transfer,
        via_agent_tool=False,
    )
    session_service = SqliteSessionService(db_path=db_path(label))
    runner = Runner(app=app, session_service=session_service)

    session_before = await session_service.get_session(
        app_name=app.name, user_id=handoff["user_id"], session_id=handoff["session_id"]
    )
    print(
        f"[{label} phase2] sessao recarregada de outro processo: "
        f"{len(session_before.events)} eventos, state={dict(session_before.state)}"
    )

    agent_to_run = runner._find_agent_to_run(session_before, app.root_agent)
    print(
        f"[{label} phase2] runner._find_agent_to_run escolheu: "
        f"{agent_to_run.name!r} (pedido original foi de {handoff['fc_author']!r})"
    )

    confirm_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=handoff["fc_id"],
                    name="adk_request_confirmation",
                    response={"confirmed": True},
                )
            )
        ],
    )

    async for event in runner.run_async(
        user_id=handoff["user_id"],
        session_id=handoff["session_id"],
        new_message=confirm_message,
    ):
        print(
            f"[{label} phase2] event author={event.author!r} "
            f"content={event.content!r}"
        )

    session_after = await session_service.get_session(
        app_name=app.name, user_id=handoff["user_id"], session_id=handoff["session_id"]
    )
    execucoes = session_after.state.get("execucoes", 0)
    print(
        f"[{label} phase2] RESULTADO: execucoes_da_tool={execucoes} "
        f"(esperado 1 se a retomada funcionou, 0 se falhou silenciosamente) "
        f"total_eventos={len(session_after.events)}"
    )


async def agenttool_demo():
    app, specialist, _tool = build_agents(
        resumable=True, disallow_transfer_to_parent=False, via_agent_tool=True
    )
    session_service = SqliteSessionService(db_path=db_path("agenttool"))
    runner = Runner(app=app, session_service=session_service)

    session = await session_service.create_session(
        app_name=app.name, user_id="apto-101"
    )
    print(f"[agenttool_demo] session_id={session.id}")

    new_message = types.Content(
        role="user",
        parts=[types.Part(text="Reserve o salao de festas para 2030-04-20")],
    )
    async for event in runner.run_async(
        user_id="apto-101", session_id=session.id, new_message=new_message
    ):
        print(
            f"[agenttool_demo] event author={event.author!r} "
            f"long_running_tool_ids={event.long_running_tool_ids!r} "
            f"content={event.content!r}"
        )

    reloaded = await session_service.get_session(
        app_name=app.name, user_id="apto-101", session_id=session.id
    )
    has_pending = any(ev.long_running_tool_ids for ev in reloaded.events)
    print(
        f"[agenttool_demo] RESULTADO: existe pendencia de confirmacao visivel "
        f"na sessao PERSISTIDA (outer)? {has_pending} "
        f"(esperado False -- a pendencia nasceu e morreu dentro do Runner "
        f"efemero/InMemorySessionService que o AgentTool cria por chamada) "
        f"state={dict(reloaded.state)}"
    )


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "success_phase1":
        await _run_phase1("success", resumable=True, disallow_transfer=True)
    elif cmd == "success_phase2":
        await _run_phase2("success", resumable=True, disallow_transfer=True)
    elif cmd == "fail_phase1":
        await _run_phase1("fail", resumable=False, disallow_transfer=True)
    elif cmd == "fail_phase2":
        await _run_phase2("fail", resumable=False, disallow_transfer=True)
    elif cmd == "agenttool_demo":
        await agenttool_demo()
    elif cmd == "custom_phase1":
        label, resumable, disallow = sys.argv[2], sys.argv[3], sys.argv[4]
        await _run_phase1(label, resumable=resumable == "1", disallow_transfer=disallow == "1")
    elif cmd == "custom_phase2":
        label, resumable, disallow = sys.argv[2], sys.argv[3], sys.argv[4]
        await _run_phase2(label, resumable=resumable == "1", disallow_transfer=disallow == "1")
    else:
        print(f"Subcomando desconhecido: {cmd}\n\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
