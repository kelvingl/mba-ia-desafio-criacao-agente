"""API FastAPI do assistente do Residencial Aurora (T10).

Expõe exatamente o contrato descrito no `ENUNCIADO.md` (seção "Contrato da
API"). As rotas de conversa (`/sessoes/...`) delegam pra `app.adk_runtime`
(Runner/App do ADK já montados nesse módulo — ver docstring dele). As rotas
de verificação (`/apartamentos/{numero}/...`) leem direto de
`app.db.condo_repo`, sem passar pelo Runner/modelo, como pedido no
enunciado.

## "Sessão não existe" -> 404 em TODAS as rotas com `{session_id}`

O contrato diz que toda rota com `{session_id}` no caminho devolve `404`
quando a sessão não existe. `adk_runtime.listar_eventos` já checa isso
(devolve `None` quando `SqliteSessionService.get_session` não acha nada).

Mas `enviar_mensagem` e `responder_confirmacao` NÃO checam: `enviar_mensagem`
chama `Runner.run_async` direto, e `responder_confirmacao` chama
`condo_repo.responder_confirmacao` primeiro (que só olha a tabela
`confirmacoes`, não a sessão do ADK) — nenhum dos dois devolve um sinal
claro de "sessão inexistente" (o `Runner` do ADK, internamente, trata sessão
ausente de formas que não dá pra garantir que cheguem aqui como uma exceção
única e estável pra capturar).

Por isso a checagem de existência da sessão é feita NESTA camada (rota),
reaproveitando `adk_runtime.listar_eventos` só pra confirmar que a sessão
existe (`None` -> sessão não existe -> 404) antes de chamar
`enviar_mensagem`/`responder_confirmacao`. É a forma mais simples e correta
de checar existência sem duplicar o acesso ao `SqliteSessionService` nem
tocar em `adk_runtime.py` (fora de escopo desta task) — o pequeno custo de
uma leitura extra de sessão por request é aceitável dado o volume do fluxo
do avaliador.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import adk_runtime
from app.db import condo_repo

app = FastAPI(title="Assistente Residencial Aurora")


class CriarSessaoBody(BaseModel):
    apartamento: str


class EnviarMensagemBody(BaseModel):
    texto: str


class ResponderConfirmacaoBody(BaseModel):
    id: str
    confirmado: bool


async def _checar_sessao_existe(session_id: str) -> None:
    """Levanta 404 se a sessão não existir. Ver docstring do módulo."""
    eventos = await adk_runtime.listar_eventos(session_id)
    if eventos is None:
        raise HTTPException(status_code=404, detail="sessão não encontrada")


@app.post("/sessoes", status_code=201)
async def criar_sessao(body: CriarSessaoBody) -> dict:
    session_id = await adk_runtime.criar_sessao(body.apartamento)
    return {"session_id": session_id}


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, body: EnviarMensagemBody) -> dict:
    await _checar_sessao_existe(session_id)
    return await adk_runtime.enviar_mensagem(session_id, body.texto)


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, body: ResponderConfirmacaoBody) -> dict:
    await _checar_sessao_existe(session_id)
    resultado = await adk_runtime.responder_confirmacao(session_id, body.id, body.confirmado)
    if resultado is None:
        raise HTTPException(status_code=409, detail="confirmação não pendente")
    return resultado


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list:
    eventos = await adk_runtime.listar_eventos(session_id)
    if eventos is None:
        raise HTTPException(status_code=404, detail="sessão não encontrada")
    return eventos


@app.get("/apartamentos/{numero}/reservas")
async def listar_reservas(numero: str) -> list:
    return condo_repo.listar_reservas(numero)


@app.get("/apartamentos/{numero}/visitantes")
async def listar_visitantes(numero: str) -> list:
    return condo_repo.listar_visitantes(numero)
