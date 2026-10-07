# Decisões de arquitetura (ADRs curtos)

Cada decisão: contexto, decisão, alternativas descartadas, e o porquê. Revisitar se um spike
(ver [`05-riscos.md`](05-riscos.md)) mostrar que a premissa está errada.

## ADR-01 — Storage: SQLite, dois arquivos separados

**Decisão**: dois bancos SQLite:

- `data/aurora_sessions.db` — gerenciado inteiramente pelo `SqliteSessionService` nativo do ADK
  (`google.adk.sessions.sqlite_session_service`; sessões, state, eventos). Não escrevemos schema
  nele à mão. *(Atualizado após o spike T04/ADR-02b: a opção original era `DatabaseSessionService`,
  mas essa classe exige a dependência extra `sqlalchemy`, não instalada e não necessária —
  `SqliteSessionService` já dá persistência real em SQLite com o que o projeto já tem, e foi a
  classe efetivamente provada funcionando no spike de confirmação com restart de processo.)*
- `data/aurora_condo.db` — escrito por nós: reservas, visitantes, confirmações pendentes, contador
  de código de reserva.

**Por quê**: a dica final do enunciado confirma que confirmação de tool + sessão persistida foi
testada funcionando com SQLite (e falhou com algumas combinações em memória). SQLite também dá
transação + índice único parcial de graça, que é exatamente o mecanismo da Garantia 5
(exclusividade no instante da gravação). Dois arquivos evitam que o schema interno do ADK colida
com o nosso.

**Alternativas descartadas**: Postgres em container (exige serviço externo documentado sem
necessidade — SQLite basta pros requisitos); tudo em memória (não sobrevive a restart, viola
Garantia 3; não serializa escritores entre processos de forma confiável pra Garantia 5 sem reinventar
locking).

## ADR-02 — Confirmação via mecanismo nativo do ADK (`require_confirmation`) + tabela própria de controle

**Decisão**: as tools `criar_reserva` (quando a área tem taxa > 0) e `autorizar_visitante` usam o
suporte nativo do ADK a confirmação de execução de tool. Além disso, mantemos uma tabela própria
`confirmacoes` em `aurora_condo.db` (id, session_id, acao, detalhes, status) que é a fonte da
verdade pro contrato HTTP (o que preenche `confirmacoes_pendentes` e decide os `409`).

**Por quê**: o enunciado pede explicitamente pra usar o mecanismo de confirmação do ADK (não
simular na mão), mas o contrato HTTP tem semântica própria (id só vale pra uma pendência, reenvio de
resposta já respondida é `409`) que precisa ser garantida mesmo depois de um restart — mais simples
de garantir com uma tabela nossa, consultada antes de tocar no Runner, do que tentando inferir esse
estado da representação interna do ADK.

**Risco associado**: a topologia de agentes (transfer vs. agent-as-tool) afeta se a resposta de
confirmação volta pro agente certo, especialmente com sessão persistida — ver spike em
[`tasks/T04-spike-confirmacao.md`](tasks/T04-spike-confirmacao.md) antes de travar isso.

## ADR-02b — Resultado do spike de confirmação (T04)

**Contexto**: T04 exigia provar, de ponta a ponta e com reinício real de processo, que a
confirmação nativa do ADK sobrevive a sessão persistida em SQLite. Não havia `GOOGLE_API_KEY` no
ambiente da execução deste spike. Em vez de ficar bloqueado, o spike (`app/scripts/spike_confirmacao.py`)
substitui o Gemini por um `BaseLlm` falso ("ScriptedLlm") que decide a próxima resposta olhando o
conteúdo da requisição, sem rede. Isso é válido porque R1 é sobre lógica 100% determinística do
próprio `Runner`/ADK (qual agente recebe a retomada), não sobre o que o modelo decide — a única
parte que de fato precisa do Gemini é "o LLM decide chamar a tool", que não é o que está em risco.
Cada fase do spike roda como um processo `uv run python` **separado** (nada em memória é
compartilhado); só o arquivo `.db` e um JSON de handoff com o id da function call pendente
atravessam a fronteira entre processos — isso é o próprio teste de restart do passo 3 da task.

**API real de confirmação confirmada no código-fonte instalado (google-adk==2.2.0)**:

- Tool: `FunctionTool(func, require_confirmation=True)` (ou callable que decide por chamada).
- Quando a tool pede confirmação, o ADK gera um evento sintético com uma `FunctionCall` chamada
  `adk_request_confirmation` (constante `REQUEST_CONFIRMATION_FUNCTION_CALL_NAME`), cujo id fica em
  `event.long_running_tool_ids`. A resposta de erro da tool em si (`{'error': 'requires confirmation...'}`)
  também é gravada, mas quem importa pra retomada é o id do `adk_request_confirmation`.
- Cliente responde enviando, como `new_message` de `runner.run_async(...)`, um
  `types.Content(role='user', parts=[types.Part(function_response=types.FunctionResponse(
  id=<id do adk_request_confirmation>, name='adk_request_confirmation', response={'confirmed': bool}))])`.
  Formato confirmado tanto pela classe `ToolConfirmation` (`google.adk.tools.tool_confirmation`)
  quanto pelo próprio `cli/cli.py` do ADK (implementação oficial do modo interativo/HITL).
- Não é necessário rastrear nem reenviar `invocation_id` nessa chamada: para um `LlmAgent` raiz em
  modo `chat` (o caso padrão, sem `Workflow`/`BaseNode`), o `Runner` resolve tudo a partir da sessão
  persistida só com o `new_message`; `invocation_id` só é relevante no caminho alternativo usado por
  nós de workflow.

**Achado principal — o fator decisivo NÃO é `App.resumability_config`**: a leitura inicial do
código (`Runner._find_agent_to_run`) sugeria que `resumability_config.is_resumable=True` seria
necessário para a retomada voltar pro especialista certo, porque existe um atalho que faz
`root_agent.find_agent(event.author)` e ignora a árvore de transferência. Testado na prática, esse
atalho **não dispara no nosso cenário**: ele só olha a função de resposta do *último* evento já
salvo, mas o último evento salvo antes da retomada é a própria `FunctionCall` pendente
(`adk_request_confirmation`), não uma resposta — então `find_matching_function_call` retorna `None`
e o atalho nunca é usado, com ou sem `resumability_config`. Quem decide de verdade, nesse ponto, é o
fallback genérico de `_find_agent_to_run`, que varre os eventos mais recentes, acha o autor do
último evento não-usuário (o especialista) e só o aceita **se ele for "transferível" até a raiz**.

Testado nas 4 combinações (processo morto e religado entre as fases, sessão SQLite em disco):

| `disallow_transfer_to_parent` no especialista | `App.resumability_config.is_resumable` | Retomada |
|---|---|---|
| `False` (padrão) | `True`  | **funciona** — volta pro especialista, tool reexecuta |
| `False` (padrão) | `False` | **funciona** — volta pro especialista, tool reexecuta |
| `True`           | `True`  | **falha silenciosa** — `Runner` escolhe o agente principal, tool nunca reexecuta, resposta 200 normal |
| `True`           | `False` | **falha silenciosa** — idêntico ao caso acima |

**Decisão**: nenhum especialista cujas tools podem pedir confirmação usa
`disallow_transfer_to_parent=True`. Esse é o único interruptor que importa pra essa armadilha.
`App.resumability_config` pode ficar ligado ou desligado sem efeito prático neste cenário (é
`@experimental` e não corrigiu nem piorou nada no teste) — mantemos **desligado** por padrão em
T08/T09 pra não carregar uma feature experimental sem necessidade comprovada; religar é trivial se
algum caso futuro (ex.: múltiplas chamadas longas encadeadas) precisar dele.

**Consequência pra ADR-06**: os 3 especialistas (reservas, visitantes, regulamento) devem ser
registrados via `sub_agents=[...]` no agente principal, **sem** `disallow_transfer_to_parent=True`
nos dois que têm tools confirmáveis (reservas e visitantes). Isso é compatível com ADR-06 como está.

**Topologia alternativa testada e descartada — `AgentTool`**: especialista acionado como
`AgentTool(agent=especialista)` em vez de `sub_agents` **não sobrevive nem dentro do mesmo
processo**, sem precisar de restart pra provar isso. `AgentTool.run_async` cria, a cada chamada, um
`Runner` e uma `InMemorySessionService()` novos e descartáveis só pra aquela chamada (ver
`google/adk/tools/agent_tool.py`). Quando a tool interna pede confirmação, o evento de
`adk_request_confirmation` (com `long_running_tool_ids`) nasce e morre dentro dessa sessão efêmera:
`AgentTool.run_async` só extrai texto puro do último evento (`_part_to_text`), e uma `FunctionCall`
não tem texto — o resultado devolvido ao agente principal é uma string vazia (`{'result': ''}`),
sem qualquer sinal de pendência. O agente principal responde normalmente, a API devolveria `200`
com `confirmacoes_pendentes: []`, e a reserva/autorização nunca seria criada. Confirmado executando
o spike (`agenttool_demo`): resposta final "Encaminhado ao especialista.", `execucoes_da_tool`
continua `0`, nenhum `long_running_tool_ids` sobrevive na sessão persistida. **Conclusão**:
`AgentTool` é estruturalmente incompatível com o mecanismo nativo de confirmação do ADK pras tools
do agente encapsulado — não é uma questão de sessão ou de restart, é a própria forma como
`AgentTool` roda o agente filho. Mantém-se a escolha de ADR-06 por `sub_agents`/transfer, agora com
prova concreta do motivo.

**Gap descoberto pra T09 — `DatabaseSessionService` (ADR-01) não está instalável como está**:
`DatabaseSessionService` (`google.adk.sessions.database_session_service`) é baseado em SQLAlchemy e
levanta `missing_extra("sqlalchemy", "db")` se `sqlalchemy` não estiver instalado — e não está
(nem está em `pyproject.toml`). O pacote JÁ traz `aiosqlite`, que é o suficiente pra
`SqliteSessionService` (`google.adk.sessions.sqlite_session_service`), uma classe nativa do ADK,
mais simples, sem SQLAlchemy, que grava eventos como JSON num arquivo SQLite de verdade. O spike
inteiro foi validado com `SqliteSessionService`, não com `DatabaseSessionService` (não dava pra
tocar em `pyproject.toml` no escopo de T04). Quem implementar T09 precisa escolher um dos dois
caminhos antes de travar isso:
  a) adicionar `sqlalchemy` (e manter `aiosqlite` como driver) em `pyproject.toml` e usar
     `DatabaseSessionService` como ADR-01 descreve; ou
  b) atualizar ADR-01 pra usar `SqliteSessionService` em vez de `DatabaseSessionService` — mesmo
     arquivo `.db`, mesma persistência real em disco, zero dependência nova, e já é a classe
     efetivamente testada neste spike.
  Recomendação: (b), por já estar provado funcionando aqui e não adicionar dependência.

**Script do spike**: `app/scripts/spike_confirmacao.py`. Decisão de manter (não apagar) — serve como
teste de regressão barato e sem custo de API pra R6 (rerodar se a versão do ADK mudar), já que não
faz chamada real ao Gemini. Subcomandos documentados no docstring do arquivo.

**O que ainda falta validar com chave real** (bloqueado por ausência de `GOOGLE_API_KEY` neste
ambiente): que o Gemini de fato decide chamar `transfer_to_agent` e a tool confirmável do jeito
esperado em uma conversa real (isso é comportamento do modelo, não do `Runner`, mas vale confirmar
uma vez com chave antes de travar T08); e o teste de concorrência do passo 14 do enunciado
(duas aprovações simultâneas), que é sobre `aurora_condo.db`/ADR-04, não sobre o ADK.

*(Atualização pós-T08/T09/T11: ambos os pontos acima foram validados com `GOOGLE_API_KEY` real.
Ver ADR-09 abaixo para um bug real de robustez encontrado no teste de concorrência do passo 14 e
já corrigido.)*

## ADR-09 — Falha do modelo ao compor o texto final não pode virar `500` numa retomada

**Contexto**: o teste do passo 14 (T11, disputa de concorrência) encontrou um bug real: em
`app/adk_runtime.py::responder_confirmacao`, depois que `condo_repo.responder_confirmacao` já
decide o resultado de negócio (aprovado), o código chamava `_runner.run_async(...)` pra retomar a
tool pausada e compor o texto final de resposta. Se essa chamada ao Gemini falhasse (ex.: `503`
transitório de "alta demanda" — reproduzido de verdade, não só simulado, inclusive durante a
verificação desta correção), a exceção propagava sem tratamento e a rota HTTP devolvia `500`. Como
`condo_repo` já tinha marcado a confirmação como `approved` antes dessa chamada, um reenvio do
mesmo id depois do `500` recebia `409` (nunca mais um `200`) — o cliente ficava sem uma resposta
"normal" pro lado perdedor da disputa, violando literalmente a Garantia 5
("recusada com uma resposta normal, sem erro de servidor").

**Decisão**: extraído um helper `_run_turno_seguro` (`app/adk_runtime.py`), usado tanto por
`enviar_mensagem` quanto por `responder_confirmacao`, que envolve o loop
`async for event in _runner.run_async(...)` em `try/except Exception`. Qualquer falha durante a
composição do texto final é logada e NUNCA propagada; os eventos já coletados (que já incluem o
resultado da tool, se ela já tiver executado) são processados normalmente por `_processar_turno`,
e só é usado um texto de fallback genérico (`_FALLBACK_SEM_TEXTO`) quando não resta nem texto final
nem confirmação pendente.

**Por quê**: a decisão de negócio (quem venceu a disputa pela reserva) já está garantida em código
antes dessa chamada — é o índice único parcial do SQLite (ADR-04), não o LLM. A falha de rede/infra
na etapa de "escrever a frase final" não deveria conseguir transformar um resultado de negócio
correto em erro de servidor pro cliente. Esta correção não muda nenhuma lógica de decisão (quem
ganha a reserva continua sendo decidido só por `condo_repo`) — só impede que uma instabilidade do
modelo generativo vaze como `500` depois que a decisão real já foi tomada.

**Validação**: reproduzido tanto com a instabilidade real do Gemini (503 genuíno, durante a própria
verificação da correção) quanto com uma falha simulada via mock de `_runner.run_async` — nos dois
casos, `responder_confirmacao` devolve uma resposta normal (nunca lança exceção) e um reenvio do
mesmo id depois continua corretamente devolvendo "não pendente" (→ `409` na API), sem reexecutar
nada.

## ADR-03 — Apartamento da sessão nunca é parâmetro de tool

**Decisão**: `POST /sessoes` grava `apartamento` em `session.state["apartamento"]` uma única vez, na
criação. Nenhuma function tool exposta ao modelo tem um parâmetro `apartamento`/`numero_apartamento`
etc. Toda tool que precisa do apartamento lê `tool_context.state["apartamento"]` internamente.

**Por quê**: é a única forma de a Garantia 2 não depender de o modelo "decidir direito" — se o
parâmetro existisse, uma mensagem bem escrita poderia induzir o modelo a preenchê-lo errado. Sem o
parâmetro, não há superfície de ataque.

**Consequência**: `consultar_disponibilidade(area, data)` não recebe nem devolve apartamento/código de
quem reservou — devolve só `livre`/`ocupada`, por tool, não por redação do prompt.

## ADR-04 — Exclusividade de reserva via índice único parcial, não via checagem prévia

**Decisão**: `CREATE UNIQUE INDEX uq_reserva_ativa ON reservas(area, data) WHERE status = 'ativa'`.
A tool de criação **tenta o INSERT direto** (dentro de uma transação `BEGIN IMMEDIATE`) e trata
`IntegrityError` como "data já ocupada" — nunca faz "SELECT pra ver se está livre" como única
defesa.

**Por quê**: é exatamente o que a Garantia 5 exige — exclusividade garantida no instante da
gravação, não numa janela de tempo entre checagem e escrita. SQLite serializa escritores por
arquivo; a segunda transação concorrente falha no constraint, não corrompe dado, não gera `500`.

## ADR-05 — Código de reserva nunca repete (mesmo cancelada): contador persistido

**Decisão**: tabela `contador_reserva` com um único registro incrementado atomicamente dentro da
mesma transação do `INSERT` da reserva. Código final: `RSV-<contador>` (zero-padded opcional).

**Por quê**: regra de negócio 5 exige não repetir nem código de reserva cancelada — um contador
monotônico persistido é mais simples de auditar do que UUID, e sobrevive a restart (Garantia 3).

## ADR-06 — Três especialistas: reservas, visitantes, regulamento

**Decisão**: agente principal + 3 especialistas (mínimo exigido é 2). Reservas e visitantes
separados porque são dois domínios de dados e de regra de confirmação distintos; regulamento
separado porque é o único que precisa de RAG e não deve vazar para o contexto dos outros dois.

**Por quê**: separar por domínio deixa cada especialista com tools de um único assunto (boa prática
de tools do curso) e isola o RAG do regulamento do resto da conversa (Garantia 4) — se regulamento
fosse parte do agente de reservas, o risco de ele carregar contexto desnecessário em perguntas de
reserva aumenta.

## ADR-07 — RAG do regulamento: chunking por artigo/capítulo + embeddings Gemini, sem servidor de vetor

**Decisão**: `regulamento.md` é fatiado em chunks por cabeçalho de capítulo/artigo em processo de
build/startup, embedado uma vez com um modelo de embedding Gemini, cache em disco
(`data/regulamento_index.json` ou `.npy`), busca por similaridade de cosseno em memória (sem
biblioteca de vetor dedicada — volume pequeno não justifica).

**Por quê**: Garantia 4 exige que o regulamento seja consultado, não carregado — nem no histórico da
sessão, nem nas instruções do agente principal. Um índice simples em memória resolve sem
infraestrutura extra.

## ADR-08 — Comando de restauração não apaga sessões

**Decisão**: o comando de restauração reseta apenas `aurora_condo.db` (reservas/visitantes/
confirmações/contador) a partir de `dados/*.json`. Não toca em `aurora_sessions.db`.

**Por quê**: o enunciado deixa a critério do desafiante; preservar sessões é mais simples de
testar (não precisa recriar sessão a cada restore) e não há requisito pedindo o apagamento.
