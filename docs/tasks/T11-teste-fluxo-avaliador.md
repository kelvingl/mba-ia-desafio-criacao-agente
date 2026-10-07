# T11 — Teste automatizado do fluxo do avaliador

**Depende de**: T10. **Bloqueia**: T13.

## Objetivo

Automatizar os passos 1–14 do "Fluxo do avaliador" do `ENUNCIADO.md` contra a API real de pé, pra
pegar regressão antes da entrega. Ver detalhes de cada caso em
[`../04-plano-testes.md`](../04-plano-testes.md).

## Passos

1. `app/scripts/fluxo_avaliador.py` (ou `tests/fluxo_avaliador.py`), usando `httpx`/`requests`
   contra `http://localhost:8000` (API precisa estar de pé — este script não sobe a API).
2. Implementar passos 2–12 em sequência, com asserts explícitos pra cada checagem do enunciado
   (não só "não deu erro" — checar conteúdo: strings proibidas nos eventos, contagens de reserva,
   presença/ausência de confirmação pendente).
3. Passo 13 (restart) **não pode ser automatizado dentro do mesmo script** sem reiniciar o
   processo da API de fora — documentar como passo manual: parar a API (`Ctrl+C`), subir de novo
   com o mesmo comando, rodar uma segunda parte do script que retoma a partir da sessão S1 já
   criada (passar `session_id` por argumento/arquivo).
4. Passo 14 (concorrência): dois requests de fato simultâneos (`asyncio.gather` com `httpx.AsyncClient`,
   ou threads) contra as duas sessões S3/S4, não sequenciais.
5. Rodar o script do zero contra uma API recém-restaurada (`restore_data` + subida) antes de
   considerar a tarefa concluída.

## Entregáveis

- Script de teste automatizado cobrindo os passos 2–12 e 14 end-to-end; passo 13 documentado como
  procedimento manual com o script dando suporte à parte "antes" e "depois" do restart.

## Critério de aceite

- Rodar o script do início ao fim (com o restart manual no meio, conforme instrução impressa pelo
  próprio script ou no README do script) sem nenhum assert falhando.
- Rodar o script duas vezes seguidas sem `restore_data` entre elas **deve** falhar em pontos
  esperados (ex.: código de reserva já existente) — serve como early-warning se a idempotência do
  contador de código (`T02`) regressar.
