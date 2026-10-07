"""Runner/App do ADK + fluxo HTTP de confirmação (T09).

Monta o `Runner`/`App` reais (não o `ScriptedLlm` do spike) em torno de
`root_agent` (`app.agents.root_agent`), com `SqliteSessionService` apontando
pra `data/aurora_sessions.db` — ADR-01 (atualizado) e ADR-02b em
`docs/01-decisoes.md`.

Topologia e config herdadas do spike (ADR-02b): os 3 especialistas já são
registrados via `sub_agents=[...]` em `root_agent` (nenhum
`disallow_transfer_to_parent=True` nos dois com tools confirmáveis —
`especialista_regulamento` é a única exceção, e não tem tool confirmável).
`App.resumability_config` fica desligado (`None`), igual à conclusão de
ADR-02b: não é o fator decisivo pra retomada funcionar e é `@experimental`.

## Decisões específicas desta task

**`user_id` do ADK é uma constante (`_USER_ID`), não o apartamento.** As 3
funções públicas que operam numa sessão já existente (`enviar_mensagem`,
`responder_confirmacao`, `listar_eventos`) recebem só `session_id` — e
`SqliteSessionService.get_session`/`run_async` exigem `app_name` + `user_id`
+ `session_id` juntos pra localizar a sessão (não dá pra buscar só pelo
`session_id`). Guardar o apartamento à parte (ex.: outro arquivo/tabela só
pra mapear session_id -> user_id) seria estado extra pra manter em sincronia
sem necessidade: o apartamento já fica em `session.state["apartamento"]`
(ADR-03), e `user_id` no ADK não tem papel de negócio aqui (não há
login/multiusuário — cada sessão já é uma conversa isolada, identificada
pelo próprio `session_id`, que o `SqliteSessionService` gera como UUID
globalmente único). Por isso todas as sessões usam o mesmo `user_id`
constante.

**Mapeamento id-da-nossa-tabela (`confirmacoes.id`) -> id-do-`adk_request_confirmation`.**
`condo_repo.criar_confirmacao` gera o próprio id (um `uuid4` novo) — não dá
pra fazer o ADK gerar o id do `adk_request_confirmation` com esse mesmo
valor. Em vez de outro arquivo/tabela só pra guardar essa correspondência,
guardamos o id do ADK **dentro do próprio `detalhes` JSON** da nossa tabela
(chave interna `_adk_confirmation_id`, prefixo `_` pra marcar "não é campo de
negócio"). `detalhes` já é uma coluna JSON de forma livre (ver
`docs/03-modelo-dados.md`), e isso sobrevive a restart de processo de graça,
sem tocar em `condo_repo.py`/`schema.sql`. A chave interna nunca escapa pra
fora deste módulo: toda vez que `confirmacoes_pendentes` é montado pra
devolver ao chamador (API), passa por `_pendentes_publicas`, que remove essa
chave antes de devolver — o contrato HTTP de `detalhes` (`docs/03-modelo-
dados.md`) continua exatamente `{"area":..., "data":...}` ou
`{"nome":..., "data":...}`, sem vazar detalhe de implementação do ADK.

**Caminho de negação (`confirmado=False`) TAMBÉM toca no `Runner`** (ver
`responder_confirmacao`) — isso mudou depois da validação inicial da T09.
Uma versão anterior deixava de enviar qualquer `FunctionResponse` pro Runner
no caso de negação (achando que bastava não responder a pendência, já que
nenhum código do `Runner` exige resolvê-la antes do próximo turno). Isso
passava num teste simples ("nega, depois manda OUTRA mensagem") mas falhava
exatamente no passo 8 do enunciado ("nega, repete o MESMO pedido, aprova"):
a `FunctionCall` pendente (`adk_request_confirmation`) ficava "viva" pra
sempre no histórico, e quando o morador repetia o mesmo pedido, o modelo via
aquela pendência antiga ainda sem resposta e respondia "como informei antes,
confirme a operação" em vez de chamar a tool de novo e gerar uma pendência
NOVA — achado real em `scripts/teste_robusto.sh`. A correção: mandar a MESMA
`FunctionResponse` de `adk_request_confirmation` nos dois casos, variando só
`response={"confirmed": confirmado}`. O próprio ADK
(`tools/function_tool.py`) já trata `confirmed=False` do jeito certo: devolve
`{'error': 'This tool call is rejected.'}` sem invocar a função de negócio
(nada é gravado) e ainda assim fecha a pendência no histórico.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from google.genai import types

from google.adk.agents.base_agent import BaseAgent
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService

from app.agents.root_agent import root_agent
from app.db import condo_repo

APP_NAME = "aurora_residencial"

# Constante deliberada — ver docstring do módulo ("user_id do ADK é uma
# constante"). Nunca é o apartamento; o apartamento vive em
# `session.state["apartamento"]` (ADR-03).
_USER_ID = "morador"

# Chave interna usada pra guardar o id do `adk_request_confirmation` dentro
# do `detalhes` da nossa tabela `confirmacoes` — ver docstring do módulo.
# Nunca aparece no `detalhes` devolvido pra fora deste módulo.
_ADK_FC_ID_KEY = "_adk_confirmation_id"

REQUEST_CONFIRMATION_FUNCTION_CALL_NAME = "adk_request_confirmation"

_BASE_DIR = Path(__file__).resolve().parents[1]
_SESSIONS_DB_PATH = _BASE_DIR / "data" / "aurora_sessions.db"
_SESSIONS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# python-dotenv já deve ter carregado o .env no startup da app principal (ver
# T10); carregamos aqui também pra este módulo funcionar isoladamente (ex.
# scripts/testes) — mesmo padrão de `app/regulamento/index.py`.
try:
    from dotenv import load_dotenv

    load_dotenv(_BASE_DIR / ".env")
except ImportError:
    pass

_app = App(name=APP_NAME, root_agent=root_agent, resumability_config=None)
_session_service = SqliteSessionService(db_path=str(_SESSIONS_DB_PATH))
_runner = Runner(app=_app, session_service=_session_service)

_logger = logging.getLogger(__name__)

_FALLBACK_SEM_TEXTO = (
    "Sua solicitação foi processada, mas não foi possível gerar uma resposta "
    "detalhada agora. Confira o resultado nas rotas de verificação ou tente "
    "de novo em instantes."
)

_FALLBACK_FALHA_SEM_EXECUCAO = (
    "Não consegui processar sua solicitação agora por uma instabilidade "
    "temporária do modelo. Nada foi executado — pode tentar enviar a "
    "mensagem de novo?"
)

# Nomes das ÚNICAS tools que gravam estado (ver app/agents/tools/*.py) --
# usadas por `_teve_execucao_real` pra decidir se é seguro reenviar a mesma
# mensagem depois de um erro transitório (ver `_run_turno_seguro`).
#
# Importante: a lista é um ALLOWLIST de escrita, não um blocklist de
# transporte. A primeira versão desta checagem excluía só
# `transfer_to_agent`/`adk_request_confirmation` e tratava qualquer outro
# function_response como "já executou, não reenvie" -- isso incluía tools de
# LEITURA (`consultar_disponibilidade`, `listar_minhas_reservas`,
# `listar_meus_visitantes`, `consultar_regulamento`), que são idempotentes e
# seguras de rodar de novo. Isso foi encontrado de verdade em
# `scripts/teste_robusto.sh`: o passo 6 chamava `consultar_disponibilidade`
# (sucesso) e DEPOIS falhava antes de chamar `reservar_area` -- a checagem
# antiga via o `function_response` de `consultar_disponibilidade`, concluía
# "já executou" e desistia de tentar de novo, deixando a reserva nunca
# criada. Só gravações têm efeito que uma reexecução poderia duplicar ou
# conflitar; por isso só elas contam como "execução real" que impede retry.
_FUNCOES_DE_ESCRITA = {"reservar_area", "cancelar_reserva", "autorizar_visitante"}

# Confirmado empiricamente (`scripts/teste_robusto.sh`, 2026-10-07): o único
# modelo acessível a esta chave/projeto é `gemini-3.1-flash-lite` (os demais
# testados devolvem 404, nem disponíveis) e ele passa por rajadas reais de
# "alta demanda" (503) que podem durar bem mais que algumas tentativas
# rápidas -- numa rajada, até 9 reenvios consecutivos da mesma mensagem
# falharam. Não há modelo alternativo pra trocar (é o único que responde),
# então a mitigação possível é dar orçamento de retry suficiente pra
# atravessar rajadas comuns sem desistir prematuramente -- sem tentar
# "esperar a rajada acabar" indefinidamente, o que deixaria o cliente HTTP
# esperando por tempo demais.
_MAX_TENTATIVAS_TURNO = 8


def _strip_detalhes(detalhes: dict[str, Any]) -> dict[str, Any]:
    """Remove a chave interna do ADK antes de expor `detalhes` pra fora."""
    return {k: v for k, v in detalhes.items() if k != _ADK_FC_ID_KEY}


def _pendentes_publicas(session_id: str) -> list[dict[str, Any]]:
    """`condo_repo.listar_confirmacoes_pendentes`, sem a chave interna do ADK."""
    pendentes = condo_repo.listar_confirmacoes_pendentes(session_id)
    return [
        {**p, "detalhes": _strip_detalhes(p["detalhes"])} for p in pendentes
    ]


def _extrair_pendencia(event: Event) -> tuple[str | None, dict[str, Any], str]:
    """Extrai (acao, detalhes, fc_id) do evento sintético `adk_request_confirmation`.

    `fc_id` é o id do próprio `adk_request_confirmation` (o que vale pra
    retomada — ver ADR-02b). `acao`/`detalhes` vêm de
    `originalFunctionCall`, a function call de negócio real que disparou a
    pendência (ex.: `reservar_area(area=..., data=...)`), embutida nos args
    do evento sintético pelo próprio ADK
    (`flows/llm_flows/functions.py:generate_request_confirmation_event`) —
    não a chamada sintética em si.
    """
    fc_id = next(iter(event.long_running_tool_ids))
    acao: str | None = None
    detalhes: dict[str, Any] = {}
    if event.content and event.content.parts:
        for part in event.content.parts:
            fc = part.function_call
            if fc and fc.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                original = fc.args.get("originalFunctionCall", {}) if fc.args else {}
                acao = original.get("name")
                detalhes = dict(original.get("args") or {})
                break
    return acao, detalhes, fc_id


def _extrair_texto_final(events: list[Event]) -> str:
    """Concatena o texto das respostas finais de texto do turno (sem function calls)."""
    textos: list[str] = []
    for event in events:
        if event.long_running_tool_ids:
            continue
        if not event.is_final_response():
            continue
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    textos.append(part.text)
    return "".join(textos)


def _processar_turno(session_id: str, events: list[Event]) -> dict[str, Any]:
    """Lógica de pós-turno comum a `enviar_mensagem` e `responder_confirmacao`.

    Se o turno parou numa confirmação pendente de tool (evento com
    `long_running_tool_ids`), registra a pendência em `condo_repo` e devolve
    `resposta=""`. Senão, extrai o texto final normalmente.
    """
    pending_event = next(
        (e for e in reversed(events) if e.long_running_tool_ids), None
    )
    if pending_event is not None:
        acao, detalhes, fc_id = _extrair_pendencia(pending_event)
        detalhes_com_fc = {**detalhes, _ADK_FC_ID_KEY: fc_id}
        condo_repo.criar_confirmacao(session_id, acao or "desconhecida", detalhes_com_fc)
        return {"resposta": "", "confirmacoes_pendentes": _pendentes_publicas(session_id)}

    texto = _extrair_texto_final(events)
    return {"resposta": texto, "confirmacoes_pendentes": _pendentes_publicas(session_id)}


def _teve_execucao_real(events: list[Event]) -> bool:
    """True se algum evento já coletado tem o `function_response` de uma tool
    que GRAVA estado (`_FUNCOES_DE_ESCRITA`) — reservar, cancelar, autorizar.

    Usada por `_run_turno_seguro` pra decidir se é seguro reenviar a mesma
    mensagem ao Runner depois de um erro transitório: se nenhuma GRAVAÇÃO
    aconteceu ainda, reenviar é equivalente ao próprio morador mandando a
    mensagem de novo (seguro — tools de leitura já executadas, como
    `consultar_disponibilidade`, são idempotentes e podem rodar de novo sem
    problema). Se uma gravação já rodou (ex.: a tool de reserva já decidiu e
    gravou), reenviar poderia tentar reprocessar uma function call que o ADK
    já considera resolvida — por isso, nesse caso, paramos de tentar e só
    usamos um texto de fallback.
    """
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            fr = part.function_response
            if fr and fr.name in _FUNCOES_DE_ESCRITA:
                return True
    return False


async def _run_turno_seguro(session_id: str, new_message: types.Content) -> dict[str, Any]:
    """Roda um turno do Runner, tenta de novo falhas transitórias com
    segurança, e NUNCA deixa uma falha do modelo virar 500 nem um falso
    "sucesso" quando nada de fato foi executado.

    Dois achados reais motivam esta função (ambos com instabilidade genuína
    do Gemini, "503 alta demanda", reproduzida de verdade nos testes, não só
    simulada):

    1. (ADR-09, teste de concorrência do passo 14) Quando a tool de negócio
       JÁ executou (ex.: `reservar_area` já decidiu quem venceu a disputa —
       isso é `condo_repo`/ADR-04, não depende do LLM) mas a chamada
       seguinte ao Gemini pra compor o texto final falha, a exceção
       propagava sem tratamento e virava um 500 HTTP — quebrando a promessa
       da Garantia 5 de que o lado perdedor recebe "uma resposta normal,
       sem erro de servidor". Aqui isso é absorvido e vira um texto de
       fallback genérico, porque a decisão de negócio já é real e definitiva.

    2. (achado posterior, `scripts/teste_robusto.sh`) Quando a falha
       acontece ANTES de qualquer tool de negócio rodar — o ADK às vezes
       absorve isso como um evento com `error_code`/`error_message` (não
       uma exceção Python) e simplesmente não produz texto nem pendência.
       Tratar isso como "processado, sem texto" (fallback do item 1) seria
       uma MENTIRA: nada foi executado, mas a resposta pareceria um sucesso
       silencioso — ex.: um pedido de cancelamento que de fato nunca chegou
       a chamar `cancelar_reserva`. Por isso, antes de desistir, tentamos de
       novo (reenviando a mesma mensagem, até `_MAX_TENTATIVAS_TURNO` vezes,
       com backoff) enquanto `_teve_execucao_real` continuar `False`. Só
       depois de esgotar as tentativas sem nenhuma execução real é que
       devolvemos um texto honesto dizendo que nada foi feito e pra tentar
       de novo — nunca o texto de "processado" do item 1.
    """
    events: list[Event] = []
    for tentativa in range(1, _MAX_TENTATIVAS_TURNO + 1):
        events = []
        erro: str | None = None
        try:
            async for event in _runner.run_async(
                user_id=_USER_ID, session_id=session_id, new_message=new_message
            ):
                events.append(event)
                if event.error_code:
                    erro = f"{event.error_code}: {event.error_message}"
        except Exception as exc:
            erro = repr(exc)
            _logger.exception(
                "Falha ao rodar/retomar turno do Runner (session_id=%s, "
                "tentativa %s/%s).",
                session_id, tentativa, _MAX_TENTATIVAS_TURNO,
            )

        if erro is None:
            break

        if _teve_execucao_real(events):
            _logger.warning(
                "Turno falhou (session_id=%s): %s -- mas uma tool de negócio "
                "já executou, não reenviando (evitar reprocessar function "
                "call já resolvida); usando fallback de 'processado'.",
                session_id, erro,
            )
            break

        if tentativa == _MAX_TENTATIVAS_TURNO:
            _logger.warning(
                "Turno falhou %s vezes (session_id=%s) sem nenhuma tool de "
                "negócio executar: %s -- desistindo, nenhuma execução real "
                "aconteceu.",
                tentativa, session_id, erro,
            )
            break

        espera = min(20, 2**tentativa)
        _logger.warning(
            "Turno falhou (session_id=%s, tentativa %s/%s): %s -- nenhuma "
            "tool de negócio executou ainda, reenviando a mesma mensagem "
            "em %ss.",
            session_id, tentativa, _MAX_TENTATIVAS_TURNO, erro, espera,
        )
        await asyncio.sleep(espera)

    resultado = _processar_turno(session_id, events)
    if not resultado["resposta"] and not resultado["confirmacoes_pendentes"]:
        resultado["resposta"] = (
            _FALLBACK_SEM_TEXTO if _teve_execucao_real(events) else _FALLBACK_FALHA_SEM_EXECUCAO
        )
    return resultado


async def criar_sessao(apartamento: str) -> str:
    """Cria sessão ADK nova, grava `apartamento` no state na criação (ADR-03)."""
    session = await _session_service.create_session(
        app_name=APP_NAME,
        user_id=_USER_ID,
        state={"apartamento": apartamento},
    )
    return session.id


async def enviar_mensagem(session_id: str, texto: str) -> dict[str, Any]:
    """Roda um turno do Runner com `texto` como mensagem de usuário.

    Nunca lança exceção pra caminhos de negócio esperados (área ocupada,
    etc.) — esses voltam como texto de conversa normal, escrito pelo próprio
    especialista a partir do retorno das tools (`condo_repo` já devolve dict,
    nunca exceção, pra esses casos — ver `app/db/condo_repo.py`).
    """
    new_message = types.Content(role="user", parts=[types.Part(text=texto)])
    return await _run_turno_seguro(session_id, new_message)


async def responder_confirmacao(
    session_id: str, confirmacao_id: str, confirmado: bool
) -> dict[str, Any] | None:
    """Responde a uma confirmação pendente da nossa tabela de controle.

    `condo_repo.responder_confirmacao` é chamado PRIMEIRO, antes de tocar no
    Runner — se devolver `ok=False` (id já respondido, id de outra sessão, ou
    inexistente), devolve `None` sem qualquer efeito colateral (quem chama
    traduz pra 409). Isso garante que reenviar a mesma confirmação já
    respondida nunca reexecuta nada.
    """
    resultado = condo_repo.responder_confirmacao(session_id, confirmacao_id, confirmado)
    if not resultado.get("ok"):
        return None

    detalhes = resultado.get("detalhes") or {}
    fc_id = detalhes.get(_ADK_FC_ID_KEY)
    if not fc_id:
        # Defensivo: não deveria acontecer (toda pendência criada por
        # `enviar_mensagem` grava `_ADK_FC_ID_KEY`), mas sem o id do ADK não
        # há como retomar a tool pausada.
        return {"resposta": "", "confirmacoes_pendentes": _pendentes_publicas(session_id)}

    # Tanto aprovação quanto negação são devolvidas ao Runner como a MESMA
    # `FunctionResponse` do `adk_request_confirmation`, só variando
    # `confirmed`. Isso NÃO é simétrico por estética: é o que fecha a
    # pendência no histórico do ADK dos dois lados.
    #
    # Achado real (`scripts/teste_robusto.sh`, passo 8 do enunciado: nega,
    # repete o mesmo pedido, aprova): uma versão anterior deste código só
    # chamava o Runner quando `confirmado=True` e, na negação, devolvia um
    # texto fixo sem nunca mandar a negação pro Runner. Isso deixava a
    # `FunctionCall` `adk_request_confirmation` da tentativa negada
    # PENDENTE pra sempre no histórico da sessão -- quando o morador repetia
    # o mesmo pedido depois, o modelo via aquela pendência antiga ainda sem
    # resposta e respondia "como informei antes, confirme a operação",
    # sem nunca chamar a tool de novo pra gerar uma pendência NOVA. O ADK
    # (`function_tool.py`) já trata `confirmed=False` do jeito certo pro
    # nosso caso: devolve `{'error': 'This tool call is rejected.'}` sem
    # invocar a função de negócio (nada é gravado), e ainda assim fecha a
    # pendência -- então não há motivo pra tratar os dois casos diferente.
    confirm_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=fc_id,
                    name=REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
                    response={"confirmed": confirmado},
                )
            )
        ],
    )
    return await _run_turno_seguro(session_id, confirm_message)


async def listar_eventos(session_id: str) -> list[dict[str, Any]] | None:
    """Eventos da sessão via `SqliteSessionService`; `None` se não existir."""
    session = await _session_service.get_session(
        app_name=APP_NAME, user_id=_USER_ID, session_id=session_id
    )
    if session is None:
        return None
    return [
        event.model_dump(mode="json", exclude_none=True) for event in session.events
    ]


__all__ = [
    "root_agent_app",
    "criar_sessao",
    "enviar_mensagem",
    "responder_confirmacao",
    "listar_eventos",
]

# Exposto só pra inspeção/debug (ex.: scripts de teste manual) — não parte
# do contrato das 5 funções pedidas pela task.
root_agent_app: BaseAgent = root_agent
