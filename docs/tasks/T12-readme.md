# T12 — README final

**Depende de**: contínuo; fecha de verdade só depois de T02, T03, T08, T09 existirem (precisa
citar arquivo+trecho reais). **Bloqueia**: entrega final.

## Objetivo

Substituir `ENUNCIADO.md` por um `README.md` na raiz com exatamente as três seções exigidas:
Arquitetura, Garantias, Como rodar (ver seção "Entregável" do `ENUNCIADO.md`).

## Conteúdo mínimo

### Arquitetura
- Cada agente (principal + 3 especialistas): responsabilidade, como é acionado, por quê. Basear em
  [`../02-arquitetura.md`](../02-arquitetura.md) e nas decisões reais tomadas em `T04`/`T08`
  (não copiar o planejado se a implementação final divergiu — descrever o que foi construído).

### Garantias
Para cada uma das 5 garantias: **arquivo e trecho de código reais** que a implementam, e por que
ela não depende do que o modelo decide. Usar como roteiro (e verificar que os caminhos ainda
existem antes de publicar):
- Garantia 1 (confirmação): `T05`/`T06` (marcação de `require_confirmation`) + `T09`
  (`responder_confirmacao` atômico) + schema `confirmacoes` (`T02`).
- Garantia 2 (sessão↔apartamento): `T09.criar_sessao` (grava `state["apartamento"]`) + ausência de
  parâmetro `apartamento` nas tools (`T05`/`T06`).
- Garantia 3 (persistência): `SqliteSessionService` em `T09` + `aurora_condo.db` em `T02`.
- Garantia 4 (regulamento consultado): `T03`/`T07` (busca por chunk) + ausência do regulamento nas
  instruções do root agent (`T08`).
- Garantia 5 (exclusividade): índice único parcial + `BEGIN IMMEDIATE` em `condo_repo.criar_reserva`
  (`T02`).

### Como rodar
- Pré-requisitos (Python 3.12+, uv, chave do Google AI Studio).
- Variáveis do `.env` (espelhar `.env.example`, atualizado por todas as tarefas que introduziram
  variável nova).
- Comando de subida (`uv run uvicorn app.main:app --port 8000`, confirmar o real usado em `T10`).
- Comando de restauração (`uv run python -m app.scripts.restore_data`, confirmar o real usado em
  `T02`).

## Critério de aceite

- As três seções existem com esses nomes.
- Cada afirmação da seção Garantias aponta pra um caminho de arquivo que existe de fato no
  repositório, e o trecho citado está presente lá (copiar e colar do arquivo real antes de
  publicar, não escrever de memória).
- Seguir o README do zero (clone limpo, `.env`, `uv sync`, comando de restauração, comando de
  subida) deixa a API respondendo com os dados iniciais — é literalmente o passo 1 do fluxo do
  avaliador.
