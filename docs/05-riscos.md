# Riscos conhecidos

## R1 — Resumo de confirmação pode não voltar pro agente certo (ALTO)

**Descrição**: o próprio enunciado avisa que a escolha de qual agente recebe a retomada de uma
confirmação pendente depende da topologia de agentes (transfer vs. agent-as-tool), dos bloqueios
de transferência, da configuração de retomada do `App` e do serviço de sessão — e que uma
combinação que funciona em memória falhou com sessão persistida entre as versões 2.2.0 e 2.9.1 do
ADK testadas pelos autores do desafio.

**Mitigação**: `tasks/T04-spike-confirmacao.md` é bloqueante — ninguém trava a topologia final dos
agentes (`tasks/T08`) nem o wiring do Runner (`tasks/T09`) antes desse spike confirmar, com sessão
persistida em SQLite e com restart do processo no meio, que a retomada funciona.

**Sinal de que deu errado**: `POST /confirmacoes` devolve `200`, não lança erro, mas a reserva/
visitante nunca é gravado. (O próprio enunciado chama isso de "armadilha silenciosa".)

## R2 — Vazamento de dados de outro apartamento via RAG ou via resposta de tool

**Descrição**: qualquer tool ou prompt que devolva texto livre contendo dado de outro apartamento
(código de reserva, nome de visitante) quebra a Garantia 2 mesmo que o *controle de acesso* esteja
certo — o enunciado testa isso lendo literalmente os eventos da sessão em busca de `RSV-4821`,
`Marina Duarte`, `302`.

**Mitigação**: nenhuma tool deve ter acesso a dados fora do apartamento da sessão — não é uma
questão de "o agente escolher não mostrar", é não ter o dado disponível pra começo de conversa.
`consultar_disponibilidade` é a única tool que toca em dado de outra reserva, e só devolve
booleano.

## R3 — Regulamento inteiro entrando no contexto via instruções ou via tool "ingênua"

**Descrição**: é fácil, por conveniência, colocar o `regulamento.md` inteiro nas instruções do
especialista "pra garantir que ele saiba tudo". Isso passa no teste manual mas quebra a Garantia 4
("nenhum evento pode conter trechos de capítulos que tratam de outros assuntos").

**Mitigação**: `consultar_regulamento` só pode devolver chunks pequenos vindos do índice de busca
(`tasks/T03`), nunca o arquivo lido direto. Testar perguntando sobre um assunto (piscina) e
inspecionando os eventos da sessão em busca de texto de capítulos não relacionados.

## R4 — Corrida na criação de reserva sendo "resolvida" só com checagem prévia

**Descrição**: implementar `se livre então grava` sem transação é a solução óbvia e errada — passa
em teste sequencial, falha no passo 14 do fluxo do avaliador (duas aprovações simultâneas).

**Mitigação**: ADR-04 (índice único parcial + `BEGIN IMMEDIATE` + captura de `IntegrityError`).
Testar literalmente com dois `curl` disparados juntos, não só com chamadas sequenciais.

## R5 — Restauração apagando o que não devia, ou não apagando o que devia

**Descrição**: comando de restauração mal escrito pode (a) também resetar `aurora_sessions.db` sem
querer, quebrando testes manuais entre execuções, ou (b) não resetar nada se o script importar o
módulo errado de conexão.

**Mitigação**: `scripts/restore_data.py` só abre `aurora_condo.db`; testar restore seguido de
restart seguido de `GET /apartamentos/101/reservas` pra confirmar o estado esperado (passo 1 do
fluxo do avaliador).

## R6 — Versão do ADK incompatível com o mecanismo de confirmação usado

**Descrição**: enunciado exige série 2, ≥2.2.0, "mais nova" permitida — mas a API de confirmação
pode variar entre 2.2.0 e versões mais novas (a própria dica final cita 2.2.0 e 2.9.1 com
comportamentos diferentes).

**Mitigação**: fixar a versão exata no `pyproject.toml` assim que o spike (`T04`) funcionar nela, e
não fazer bump de versão depois sem re-rodar o spike.
