# Residencial Aurora — assistente virtual (Google ADK + FastAPI)

Assistente dos moradores do Residencial Aurora: reserva de áreas comuns, autorização de
visitantes e dúvidas sobre o regulamento interno, por chat, com as regras de negócio garantidas
em código — nunca por aquilo que o modelo "decide" a partir da conversa.

Este README documenta o que foi efetivamente construído (código em `app/`). O enunciado
original do desafio está preservado, intocado, em [`ENUNCIADO.md`](ENUNCIADO.md). As decisões de
arquitetura e os motivos de cada uma, incluindo caminhos alternativos testados e descartados,
estão em [`docs/01-decisoes.md`](docs/01-decisoes.md) (ADRs) — este README resume e aponta pra
lá quando for útil.

## Arquitetura

Um agente principal (`agente_principal`) e três especialistas, todos `LlmAgent` do ADK,
registrados como `sub_agents` do principal (`app/agents/root_agent.py`):

```python
root_agent = LlmAgent(
    name="agente_principal",
    model=MODEL,
    ...
    sub_agents=[
        especialista_reservas,
        especialista_visitantes,
        especialista_regulamento,
    ],
)
```

### Agente principal (`app/agents/root_agent.py`)

**Responsabilidade**: só roteamento. Não declara nenhuma tool de negócio — nunca reserva, cancela,
autoriza visitante nem busca no regulamento ele mesmo. Decide, pelo assunto da mensagem, para qual
dos três especialistas transferir a conversa (e pergunta ao morador quando não tem certeza).

**Como é acionado**: é o agente raiz do `App`/`Runner` (`app/adk_runtime.py`) — toda mensagem do
morador chega primeiro a ele.

**Por quê**: isolar o roteamento do conteúdo evita que o agente que decide o caminho também
precise carregar conhecimento de domínio (reservas, visitantes, regulamento) nas próprias
instruções — em particular, ele nunca recebe o conteúdo do regulamento (ver Garantia 4).

### Especialista de reservas (`app/agents/especialista_reservas.py`)

**Responsabilidade**: reservar, consultar disponibilidade, listar e cancelar reservas de áreas
comuns. Tools: `reservar_area_tool`, `cancelar_reserva_tool`, `listar_minhas_reservas_tool`,
`consultar_disponibilidade`.

**Como é acionado**: via `transfer_to_agent` do agente principal (`sub_agents=[...]`), nunca via
`AgentTool`. `disallow_transfer_to_parent=False` (padrão, deliberado).

**Por quê transfer e não `AgentTool`**: esse especialista tem uma tool confirmável
(`reservar_area`, quando a área tem taxa). O spike T04 (ADR-02b em `docs/01-decisoes.md`) provou,
lendo o código-fonte instalado do ADK (`google/adk/tools/agent_tool.py`) e reproduzindo em
execução, que `AgentTool.run_async` cria "a cada chamada, um `Runner` e uma
`InMemorySessionService()` novos e descartáveis só pra aquela chamada". Quando a tool interna pede
confirmação, o evento de pendência "nasce e morre dentro dessa sessão efêmera" — `AgentTool`
"só extrai texto puro do último evento (`_part_to_text`), e uma `FunctionCall` não tem texto — o
resultado devolvido ao agente principal é uma string vazia (`{'result': ''}`), sem qualquer sinal
de pendência". Ou seja: a API responderia `200` com `confirmacoes_pendentes: []` e a reserva nunca
seria criada, violando a Garantia 1 de forma estrutural, não por bug pontual. Por isso a topologia
é `sub_agents`/transfer.

### Especialista de visitantes (`app/agents/especialista_visitantes.py`)

**Responsabilidade**: autorizar entrada de visitantes e listar visitantes já autorizados. Tools:
`autorizar_visitante_tool` (sempre confirmável), `listar_meus_visitantes_tool`.

**Como é acionado**: mesma topologia do especialista de reservas — `sub_agents`, transfer,
`disallow_transfer_to_parent=False`. É, nas palavras do próprio módulo, "o especialista onde o
achado do spike T04 mais importa": `autorizar_visitante_tool` é *sempre* confirmável
(`require_confirmation=True` incondicional), então `True` em `disallow_transfer_to_parent` aqui
"quebraria silenciosamente a retomada da confirmação de autorização de entrada".

**Por quê separado de reservas**: são dois domínios de dados e de regra de confirmação distintos
(ADR-06) — manter cada especialista com tools de um único assunto é a boa prática de tools do
curso, e evita que um bug de roteamento num domínio arraste o outro.

### Especialista de regulamento (`app/agents/especialista_regulamento.py`)

**Responsabilidade**: responder dúvidas sobre o regulamento interno, sempre via a tool
`consultar_regulamento` — nunca "de memória própria" (instrução explícita do agente).

**Como é acionado**: também via `sub_agents`/transfer, mas com `disallow_transfer_to_parent=True`
— a única exceção entre os três. A tool deste especialista (`consultar_regulamento`) nunca é
confirmável, então ele está fora do risco provado em ADR-02b (aquele achado só importa pra
retomar uma confirmação pendente no especialista certo depois de restart). Sem esse risco, `True`
aqui evita que o `Runner` reaproveite este especialista em todo turno seguinte quando o assunto já
mudou — o fallback cai direto no agente principal, que decide de novo pelas próprias instruções de
roteamento.

**Por quê é um especialista separado dos outros dois**: é o único que precisa de RAG sobre
`dados/regulamento.md`, e isolá-lo evita que o conteúdo do regulamento "vaze" para o contexto dos
especialistas de reservas/visitantes (ADR-06) — se o regulamento fizesse parte do agente de
reservas, por exemplo, o risco de carregar contexto desnecessário em perguntas de reserva
aumentaria, o que vai contra a Garantia 4.

## Garantias

Para cada uma das cinco garantias do enunciado: o arquivo e o trecho real que a implementa, e por
que ela não depende do que o modelo decide.

### Garantia 1 — cobrança ou acesso só com confirmação

- `app/agents/tools/reservas_tools.py` marca `reservar_area_tool` com `require_confirmation`
  *condicional* (um `callable`, não um `bool` fixo), porque só áreas com taxa exigem confirmação:

  ```python
  def _requer_confirmacao_reserva(
      area: str, data: str, tool_context: ToolContext
  ) -> bool:
      info_area = condo_repo.obter_area(area)
      taxa = info_area["taxa"] if info_area else 0
      return taxa > 0
  ```

- `app/agents/tools/visitantes_tools.py` marca `autorizar_visitante_tool` com confirmação
  *incondicional*, porque autorizar visitante sempre libera acesso:

  ```python
  autorizar_visitante_tool = FunctionTool(autorizar_visitante, require_confirmation=True)
  ```

- `app/adk_runtime.py::responder_confirmacao` consulta `condo_repo.responder_confirmacao`
  **antes** de tocar no `Runner`:

  ```python
  resultado = condo_repo.responder_confirmacao(session_id, confirmacao_id, confirmado)
  if not resultado.get("ok"):
      return None
  ```

  e `condo_repo.responder_confirmacao` (`app/db/condo_repo.py`) só transiciona a linha se
  `status = 'pending'` ainda for verdade no mesmo `UPDATE` atômico:

  ```python
  cur = conn.execute(
      "UPDATE confirmacoes SET status = ?"
      " WHERE id = ? AND session_id = ? AND status = 'pending'",
      (novo_status, confirmacao_id, session_id),
  )
  if cur.rowcount == 0:
      conn.execute("ROLLBACK")
      return {"ok": False}
  ```

**Por que não depende do modelo**: a decisão de pedir confirmação é feita pelo ADK a partir do
registro da tool (`require_confirmation`), não por o modelo "concordar em pedir". E o `409`/"não
executa de novo" é decidido consultando a tabela `confirmacoes` antes de qualquer chamada ao
`Runner`/Gemini — mesmo que o morador escreva "já estou confirmando aqui", nada no texto da
mensagem chega a essa checagem de SQL.

**Aprovação e negação fecham a pendência do ADK da mesma forma.** `responder_confirmacao`
(`app/adk_runtime.py`) envia ao `Runner` a mesma `FunctionResponse` de `adk_request_confirmation`
nos dois casos, só variando `response={"confirmed": confirmado}` — achado real via
`scripts/teste_robusto.sh` (passo 8: nega, repete o mesmo pedido, aprova): uma versão anterior só
chamava o `Runner` na aprovação, deixando a pendência da negação sem resposta no histórico; ao
repetir o mesmo pedido depois, o modelo via aquela pendência antiga ainda aberta e se recusava a
pedir confirmação de novo. O próprio ADK (`tools/function_tool.py`) já trata `confirmed=False` sem
invocar a função de negócio (`{'error': 'This tool call is rejected.'}`), então nada é gravado em
nenhum dos dois caminhos — só a forma de fechar a pendência mudou.

### Garantia 2 — cada sessão pertence a um apartamento

- `app/adk_runtime.py::criar_sessao` grava o apartamento no state uma única vez, na criação:

  ```python
  async def criar_sessao(apartamento: str) -> str:
      session = await _session_service.create_session(
          app_name=APP_NAME,
          user_id=_USER_ID,
          state={"apartamento": apartamento},
      )
      return session.id
  ```

- Qualquer tool de negócio lê esse valor do state, nunca de um parâmetro — ex.
  `app/agents/tools/reservas_tools.py::reservar_area`:

  ```python
  def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
      apartamento = tool_context.state["apartamento"]
      ...
  ```

**Por que não depende do modelo**: a assinatura de `reservar_area` (e de todas as outras tools de
negócio) não tem parâmetro `apartamento`/`numero_apartamento` — não existe campo que o modelo
possa preencher errado. Mesmo que o morador diga "sou do 302", não há onde esse texto entraria
como apartamento numa chamada de tool; o valor usado é sempre o gravado na sessão.

### Garantia 3 — nada se perde no reinício

- `app/adk_runtime.py` monta o `Runner` com `SqliteSessionService` apontando para
  `data/aurora_sessions.db`:

  ```python
  _SESSIONS_DB_PATH = _BASE_DIR / "data" / "aurora_sessions.db"
  ...
  _session_service = SqliteSessionService(db_path=str(_SESSIONS_DB_PATH))
  _runner = Runner(app=_app, session_service=_session_service)
  ```

- `app/db/condo_repo.py` grava reservas/visitantes/confirmações num segundo arquivo SQLite
  (`data/aurora_condo.db`), definido pelo schema de `app/db/schema.sql`:

  ```python
  DB_PATH = BASE_DIR / "data" / "aurora_condo.db"
  ```

  ```sql
  CREATE TABLE reservas (
      codigo      TEXT PRIMARY KEY,
      apartamento TEXT NOT NULL,
      area        TEXT NOT NULL,
      data        TEXT NOT NULL,   -- AAAA-MM-DD
      status      TEXT NOT NULL CHECK (status IN ('ativa', 'cancelada'))
  );
  ```

**Por que não depende do modelo**: os dois bancos são arquivos reais em disco, escritos por SQL
síncrono (sessões/eventos pelo `SqliteSessionService` nativo do ADK; reservas/visitantes/
confirmações por `condo_repo`) — nada fica só em memória de processo. Reiniciar a API não apaga
nenhum dos dois arquivos.

### Garantia 4 — o regulamento é consultado, não carregado

- `app/regulamento/chunker.py` fatia `dados/regulamento.md` por artigo (não por capítulo inteiro,
  nem o arquivo inteiro), prefixado com o capítulo:

  ```python
  def _fechar_artigo() -> None:
      if artigo_linhas and any(linha.strip() for linha in artigo_linhas):
          corpo = "\n".join(artigo_linhas).strip()
          if capitulo_atual:
              chunks.append(f"{capitulo_atual}\n\n{corpo}")
  ```

- `app/regulamento/index.py::buscar` devolve só os `k` chunks mais próximos por similaridade de
  cosseno, nunca o documento inteiro:

  ```python
  def buscar(pergunta: str, k: int = 2) -> list[str]:
      ...
      return [texto for texto, _ in pontuados[:k]]
  ```

- `app/agents/tools/regulamento_tools.py::consultar_regulamento` não tem nenhum caminho de
  fallback que leia o arquivo completo — se a busca não achar nada, devolve uma frase curta:

  ```python
  _SEM_RESULTADO = "Não encontrei nada no regulamento sobre esse assunto."
  ...
  if not trechos:
      return _SEM_RESULTADO
  ```

- `app/agents/root_agent.py` — a instrução do agente principal não cita o conteúdo do regulamento
  em nenhum momento, só o critério de roteamento ("transfira pro especialista de regulamento"); o
  próprio docstring do módulo documenta essa restrição: "Garantia 4: nenhum trecho de
  `dados/regulamento.md` pode aparecer aqui, nem resumido nem copiado".

**Por que não depende do modelo**: o tamanho do texto que entra no histórico da sessão é limitado
pelo código (fatiamento + top-`k`), não por o modelo "decidir resumir" ou "escolher não copiar o
documento inteiro" — não há tool nem instrução que exponha o arquivo completo para ser copiado.

### Garantia 5 — dois moradores, uma reserva

- `app/db/schema.sql` declara um índice único **parcial**, que só vale para reservas ativas:

  ```sql
  CREATE UNIQUE INDEX uq_reserva_ativa ON reservas(area, data) WHERE status = 'ativa';
  ```

- `app/db/condo_repo.py::criar_reserva` abre `BEGIN IMMEDIATE`, tenta o `INSERT` direto (nunca um
  "SELECT pra ver se está livre" como única defesa) e trata a violação do índice como resultado de
  negócio, não como erro:

  ```python
  conn.execute("BEGIN IMMEDIATE")
  try:
      ...
      conn.execute(
          "INSERT INTO reservas (codigo, apartamento, area, data, status)"
          " VALUES (?, ?, ?, ?, 'ativa')",
          (codigo, apartamento, area, data),
      )
  except sqlite3.IntegrityError:
      conn.execute("ROLLBACK")
      return {"ok": False, "motivo": "ocupada"}
  conn.execute("COMMIT")
  return {"ok": True, "codigo": codigo}
  ```

**Por que não depende do modelo**: a exclusividade é imposta pelo SQLite no instante do `COMMIT`
(constraint de índice), não por uma checagem prévia que o código faz e que poderia perder uma
corrida entre "consultar disponibilidade" e "gravar". Mesmo que o modelo pule a chamada a
`consultar_disponibilidade`, o `INSERT` concorrente perdedor sempre recebe `IntegrityError`.

Essa garantia foi de fato testada sob corrida real, não só verificada na lógica — e o processo de
testá-la sob um ambiente Docker isolado (`scripts/teste_robusto.sh`) encontrou bugs reais de
robustez em torno dela, todos documentados em ADR-09 (`docs/01-decisoes.md`) e corrigidos em
`app/adk_runtime.py::_run_turno_seguro`:

```python
async def _run_turno_seguro(session_id: str, new_message: types.Content) -> dict[str, Any]:
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
            _logger.exception(...)

        if erro is None:
            break
        if _teve_execucao_real(events):
            break  # já gravou -- não reenviar, só usar fallback de "processado"
        if tentativa == _MAX_TENTATIVAS_TURNO:
            break  # esgotou tentativas sem nenhuma gravação -- fallback honesto
        await asyncio.sleep(min(20, 2**tentativa))

    resultado = _processar_turno(session_id, events)
    if not resultado["resposta"] and not resultado["confirmacoes_pendentes"]:
        resultado["resposta"] = (
            _FALLBACK_SEM_TEXTO if _teve_execucao_real(events) else _FALLBACK_FALHA_SEM_EXECUCAO
        )
    return resultado
```

Dois achados reais motivaram esta função (o único modelo Gemini acessível a esta chave,
`gemini-3.1-flash-lite`, passa por rajadas reais de "alta demanda"/`503`, reproduzidas de verdade
nos testes — ver ADR-09):

1. Quando a tool de negócio **já executou** (ex.: `reservar_area` já decidiu quem venceu a disputa
   — isso é `condo_repo`/índice único, não depende do LLM) e só a chamada seguinte ao Gemini pra
   compor o texto final falha, a exceção propagava sem tratamento e virava um `500` HTTP —
   quebrando a promessa de "resposta normal, sem erro de servidor" pro lado perdedor.
2. Quando a falha acontece **antes** de qualquer tool de negócio rodar, devolver um texto de
   fallback genérico seria uma mentira (pareceria sucesso sem nada ter sido executado) — por isso a
   função reenvia a mesma mensagem (seguro: nenhuma gravação aconteceu ainda) até
   `_teve_execucao_real` virar verdadeiro ou esgotar `_MAX_TENTATIVAS_TURNO`, e só desiste com um
   texto honesto de falha, nunca fingindo sucesso.

Nenhuma dessas correções muda a lógica de decisão (quem ganha a reserva continua sendo decidido só
por `condo_repo`/índice único) — só garantem que uma instabilidade do modelo generativo nunca vaze
como erro de servidor nem como um falso sucesso.

## Como rodar

### Pré-requisitos

- Python 3.12 ou superior.
- [`uv`](https://docs.astral.sh/uv/).
- Uma chave de API do Google AI Studio (Gemini).

### Variáveis do `.env`

Copie `.env.example` para `.env` e preencha. Hoje o arquivo tem uma única variável:

```
GOOGLE_API_KEY=
```

### Instalar dependências

```
uv sync
```

Fixa `google-adk==2.2.0` (série 2, ≥ 2.2.0) em `pyproject.toml`.

### Restaurar os dados iniciais

```
uv run python -m app.scripts.restore_data
```

Apaga e recria `data/aurora_condo.db` a partir de `dados/*.json` (reservas, visitantes,
confirmações e o contador de código de reserva). Não toca em `data/aurora_sessions.db` — as
sessões do ADK sobrevivem a uma restauração de dados (ADR-08).

### Subir a API

```
uv run uvicorn app.main:app --port 8000
```

A API responde em `http://localhost:8000`. Na primeira subida, a primeira pergunta sobre o
regulamento constrói e cacheia o índice de embeddings em `data/regulamento_index.json`
(idempotente — só reprocessa se `dados/regulamento.md` mudar).

Para confirmar que subiu com os dados certos:

```
curl http://localhost:8000/apartamentos/101/reservas
curl http://localhost:8000/apartamentos/302/visitantes
```

### Opcional — validar o fluxo completo do avaliador

`app/scripts/fluxo_avaliador.py` automatiza os passos 2–14 do "Fluxo do avaliador" do
`ENUNCIADO.md` (criação de sessões, cancelamentos, confirmações, restart manual no meio, disputa
de concorrência) contra uma API já no ar. Não é parte do contrato — é um extra de qualidade usado
durante o desenvolvimento (T11) para provar as cinco garantias ponta a ponta:

```
uv run python -m app.scripts.fluxo_avaliador parte1
# reinicie a API manualmente aqui, sem rodar restore_data
uv run python -m app.scripts.fluxo_avaliador parte2
uv run python -m app.scripts.fluxo_avaliador parte3
```

### Opcional — teste robusto de ponta a ponta em Docker

`scripts/teste_robusto.sh` sobe a API num container Docker isolado (`Dockerfile` +
`docker-compose.yml` — não fazem parte do contrato, que não exige serviço externo), restaura os
dados, roda `fluxo_avaliador.py` por dentro do container com um **restart de processo real**
(`docker compose restart`) e uma **disputa de concorrência real**, e termina com checagens
estáticas do repositório (versão do ADK, `.env` fora do git, etc.). Não precisa de `uv`/Python no
host, só Docker:

```
scripts/teste_robusto.sh --reset-data
```

Foi este script, rodado contra o Gemini real, que encontrou e permitiu corrigir os bugs de
robustez documentados em ADR-09 (`docs/01-decisoes.md`).
