# Decisões de arquitetura (ADRs curtos)

Cada decisão: contexto, decisão, alternativas descartadas, e o porquê. Revisitar se um spike
(ver [`05-riscos.md`](05-riscos.md)) mostrar que a premissa está errada.

## ADR-01 — Storage: SQLite, dois arquivos separados

**Decisão**: dois bancos SQLite:

- `data/aurora_sessions.db` — gerenciado inteiramente pelo `DatabaseSessionService` do ADK
  (sessões, state, eventos). Não escrevemos schema nele à mão.
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
