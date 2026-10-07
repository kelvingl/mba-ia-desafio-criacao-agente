# T02 — Schema + repo de dados do condomínio

**Depende de**: T00. **Bloqueia**: T05, T06, T10.

## Objetivo

Implementar `data/aurora_condo.db` (schema, acesso) e o seed/restore a partir de `dados/*.json`,
seguindo exatamente o contrato de funções em
[`../03-modelo-dados.md`](../03-modelo-dados.md#appdbcondo_repopy--funções-expostas).

## Passos

1. `app/db/schema.sql` (ou DDL embutido em Python) com as 4 tabelas do contrato (`reservas`,
   `visitantes`, `confirmacoes`, `contador_reserva`), incluindo o índice único parcial
   `uq_reserva_ativa` (ver ADR-04 em `../01-decisoes.md`).
2. `app/db/seed.py`: lê `dados/apartamentos.json`, `dados/areas.json`, `dados/reservas.json`,
   `dados/visitantes.json` e popula `aurora_condo.db` do zero (tabelas limpas antes de inserir).
   `apartamentos.json` e `areas.json` podem ficar só em memória (lidos a cada boot) ou em tabelas
   auxiliares — decisão livre, desde que `obter_area` funcione.
3. `app/scripts/restore_data.py`: apaga/recria `aurora_condo.db` e chama `seed.py`. Comando
   documentado no README (`T12`). **Não toca em `aurora_sessions.db`** (ADR-08).
4. `app/db/condo_repo.py`: implementar todas as funções do contrato, com atenção especial a:
   - `criar_reserva`: `BEGIN IMMEDIATE`, `INSERT`, capturar `sqlite3.IntegrityError` do índice
     único e devolver `{"ok": False, "motivo": "ocupada"}` em vez de propagar a exceção.
   - Geração de código: ler+incrementar `contador_reserva` na mesma transação do insert.
   - `responder_confirmacao`: transição atômica condicionada a `status='pending'` E `session_id`
     batendo — é o que garante o `409` em reenvio (ver Garantia 1).
5. Testes manuais mínimos (pode ser um script solto, não precisa de framework de teste):
   - Duas chamadas concorrentes a `criar_reserva` pra mesma área/data → uma `ok=True`, outra
     `ok=False, motivo=ocupada` (usar threads ou dois processos `uv run python -c ...` disparados
     juntos).
   - Restart do processo Python entre duas chamadas → dado persiste.

## Entregáveis

- `app/db/schema.sql`, `app/db/seed.py`, `app/db/condo_repo.py`, `app/scripts/restore_data.py`.
- `data/aurora_condo.db` gerado e ignorado pelo git.

## Critério de aceite

- Rodar `uv run python -m app.scripts.restore_data` seguido de uma consulta confirma
  `RSV-1377` em `101` e Marina Duarte em `302` (mesmos dados citados no passo 1 do fluxo do
  avaliador).
- Teste de concorrência (passo acima) nunca produz duas reservas ativas pra mesma área/data.
- Nenhuma função do módulo lança exceção não tratada para quem a chama em caminho esperado (área
  ocupada, confirmação já respondida, etc. são retornos de domínio, não exceções).
