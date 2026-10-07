#!/usr/bin/env bash
# Teste robusto de ponta a ponta do assistente do Residencial Aurora,
# rodando a API dentro de um container Docker isolado (ambiente limpo e
# reproduzível, equivalente ao "clone limpo" do passo 1 do fluxo do
# avaliador do ENUNCIADO.md) e exercitando as 5 garantias via HTTP real,
# incluindo um RESTART DE PROCESSO de verdade (`docker compose restart`,
# não só reenvio de request) e uma DISPUTA DE CONCORRÊNCIA real (duas
# aprovações em paralelo).
#
# Não substitui `app/scripts/fluxo_avaliador.py` (T11) -- reaproveita ele
# integralmente, rodando dentro do container. O valor deste script é o
# ambiente: ninguém precisa ter `uv`, Python 3.12 ou um venv configurado no
# host para rodar a validação completa -- só Docker e Docker Compose.
#
# Uso:
#   scripts/teste_robusto.sh              # build + up + fluxo completo + down
#   scripts/teste_robusto.sh --reset-data  # como acima, mas zera data/ antes
#                                           # (estado 100% limpo, como um
#                                           # clone novo)
#   scripts/teste_robusto.sh --keep        # não derruba o container no final
#                                           # (útil para inspecionar depois)
#   scripts/teste_robusto.sh --help
#
# Pré-requisito: `.env` na raiz do repo com GOOGLE_API_KEY real (copie de
# `.env.example`). O script recusa rodar sem isso, com uma mensagem clara.
#
# Saída: resumo PASS/FAIL ao final; código de saída 0 só se absolutamente
# tudo passou (adequado para CI).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO_ROOT="$(pwd)"
COMPOSE="docker compose"
SERVICE="api"
BASE_URL="http://localhost:8000"

RESET_DATA=0
KEEP=0
for arg in "$@"; do
  case "$arg" in
    --reset-data) RESET_DATA=1 ;;
    --keep) KEEP=1 ;;
    --help|-h)
      sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Argumento desconhecido: $arg (use --help)" >&2
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Contabilidade de resultado -- cada checagem chama `check` (continua mesmo
# se falhar, para rodar o máximo de passos e dar um relatório completo) ou
# `fail_fast` (aborta imediatamente -- usado só para pré-condições sem as
# quais nada mais faz sentido, como a API nunca subir).
# ---------------------------------------------------------------------------
declare -a RESULTADOS=()
FALHAS=0

check() {
  local descricao="$1"
  shift
  if "$@"; then
    RESULTADOS+=("OK   - $descricao")
    echo "[OK]   $descricao"
  else
    RESULTADOS+=("FAIL - $descricao")
    FALHAS=$((FALHAS + 1))
    echo "[FAIL] $descricao"
  fi
}

fail_fast() {
  local descricao="$1"
  echo "[FATAL] $descricao" >&2
  echo "" >&2
  echo "--- últimas 100 linhas de log do container ($SERVICE) ---" >&2
  $COMPOSE logs --tail=100 "$SERVICE" 2>&1 || true
  exit 1
}

# ---------------------------------------------------------------------------
# Teardown -- roda sempre que o script termina (sucesso, falha ou Ctrl+C),
# a menos que --keep tenha sido passado.
# ---------------------------------------------------------------------------
cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo ""
    echo ">>> --keep passado: container continua no ar (docker compose down manual quando quiser)."
    return
  fi
  echo ""
  echo ">>> Derrubando o container de teste..."
  $COMPOSE down >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pré-condições
# ---------------------------------------------------------------------------
echo "=== Pré-condições ==="

command -v docker >/dev/null 2>&1 || fail_fast "docker não encontrado no PATH"
$COMPOSE version >/dev/null 2>&1 || fail_fast "'docker compose' não disponível"
command -v curl >/dev/null 2>&1 || fail_fast "curl não encontrado no PATH"

if [ ! -f "$REPO_ROOT/.env" ]; then
  fail_fast "não existe .env na raiz do repo -- copie .env.example para .env e preencha GOOGLE_API_KEY antes de rodar este teste"
fi
if ! grep -qE '^GOOGLE_API_KEY=.+' "$REPO_ROOT/.env"; then
  fail_fast ".env existe mas GOOGLE_API_KEY parece vazia -- preencha com uma chave real do Google AI Studio"
fi
echo "[OK]   .env presente com GOOGLE_API_KEY preenchida"

if [ "$RESET_DATA" -eq 1 ]; then
  echo ">>> --reset-data: limpando ./data (estado 100% limpo, como clone novo)"
  rm -rf "$REPO_ROOT/data"
fi
mkdir -p "$REPO_ROOT/data"

# ---------------------------------------------------------------------------
# Build + up (equivalente ao passo 1 do fluxo do avaliador: "clone limpo,
# uv sync, sobe o que for necessário")
# ---------------------------------------------------------------------------
echo ""
echo "=== Build + subida do container ==="
$COMPOSE build
$COMPOSE up -d

wait_api_up() {
  local tentativas=30
  local i
  for ((i = 1; i <= tentativas; i++)); do
    if curl -fsS -o /dev/null --max-time 2 "$BASE_URL/apartamentos/000/reservas" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo ">>> Esperando a API responder em $BASE_URL ..."
wait_api_up || fail_fast "API não respondeu em $BASE_URL depois de ~60s"
echo "[OK]   API respondendo"

# ---------------------------------------------------------------------------
# Restaura os dados do seed (reservas/visitantes voltam ao estado de
# dados/*.json) dentro do container -- equivalente ao comando de restauração
# do README, rodado no ambiente limpo.
# ---------------------------------------------------------------------------
echo ""
echo "=== Restaurar dados iniciais ==="
check "restore_data roda sem erro dentro do container" \
  $COMPOSE exec -T "$SERVICE" uv run python -m app.scripts.restore_data

echo ""
echo "=== Passo 1 (smoke manual) — dados iniciais batem com o enunciado ==="
RESERVAS_101="$(curl -fsS "$BASE_URL/apartamentos/101/reservas")"
VISITANTES_302="$(curl -fsS "$BASE_URL/apartamentos/302/visitantes")"
check "GET /apartamentos/101/reservas contém RSV-1377" \
  bash -c "echo '$RESERVAS_101' | grep -q 'RSV-1377'"
check "GET /apartamentos/302/visitantes contém Marina Duarte" \
  bash -c "echo '$VISITANTES_302' | grep -q 'Marina Duarte'"

# ---------------------------------------------------------------------------
# Fluxo do avaliador (T11), rodado DENTRO do container -- nenhuma
# dependência do host além de docker/docker compose/curl.
# ---------------------------------------------------------------------------
echo ""
echo "=== Fluxo do avaliador — parte 1 (passos 2-12) ==="
check "parte1 (passos 2-12) passa todos os asserts" \
  $COMPOSE exec -T "$SERVICE" uv run python -m app.scripts.fluxo_avaliador parte1

echo ""
echo "=== Restart REAL do processo (passo 13 / Garantia 3) ==="
echo ">>> docker compose restart $SERVICE (mata e sobe o processo de novo, SEM restore_data)"
$COMPOSE restart "$SERVICE"
wait_api_up || fail_fast "API não voltou a responder depois do restart"
echo "[OK]   API voltou a responder depois do restart"

check "parte2 (passo 13, após restart) passa todos os asserts" \
  $COMPOSE exec -T "$SERVICE" uv run python -m app.scripts.fluxo_avaliador parte2

echo ""
echo "=== Disputa de concorrência real (passo 14 / Garantia 5) ==="
check "parte3 (passo 14, aprovações em paralelo) passa todos os asserts" \
  $COMPOSE exec -T "$SERVICE" uv run python -m app.scripts.fluxo_avaliador parte3

# ---------------------------------------------------------------------------
# Checagens estáticas do repositório (não precisam da API/Docker) --
# espelham o passo 15 do fluxo do avaliador (inspeção de repositório) e os
# critérios de aceite de "Execução e entrega" / "Arquitetura".
# ---------------------------------------------------------------------------
echo ""
echo "=== Checagens estáticas do repositório (passo 15) ==="

check "google-adk fixado na série 2, >= 2.2.0, em pyproject.toml" \
  grep -qE '^\s*"google-adk==2\.[2-9][0-9]*(\.[0-9]+)?"' "$REPO_ROOT/pyproject.toml"

check ".env não está versionado no git" \
  bash -c "! git -C '$REPO_ROOT' ls-files --error-unmatch .env >/dev/null 2>&1"

check ".env.example existe e lista GOOGLE_API_KEY" \
  grep -q "GOOGLE_API_KEY" "$REPO_ROOT/.env.example"

check "dados/ sem alterações não commitadas (seed intocado)" \
  bash -c "git -C '$REPO_ROOT' diff --quiet -- dados/ && git -C '$REPO_ROOT' diff --cached --quiet -- dados/"

check "nenhuma tool de negócio declara parâmetro de apartamento" \
  bash -c "! grep -nE 'def (reservar_area|cancelar_reserva|listar_minhas_reservas|autorizar_visitante|listar_meus_visitantes|consultar_disponibilidade)\\(' '$REPO_ROOT'/app/agents/tools/*.py | grep -Ei 'apartamento\\s*:|numero_apartamento'"

check "root_agent.py não contém trechos do regulamento (shingles de 8 palavras)" \
  python3 "$REPO_ROOT/scripts/_check_sem_regulamento.py"

check "nenhuma chave de API (padrão AIza...) commitada no repositório" \
  bash -c "! git -C '$REPO_ROOT' grep -IEn 'AIza[0-9A-Za-z_-]{30,}' -- . ':(exclude).env' >/dev/null 2>&1"

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
echo ""
echo "=== Resumo ==="
for linha in "${RESULTADOS[@]}"; do
  echo "$linha"
done
echo ""
if [ "$FALHAS" -eq 0 ]; then
  echo "=== TODAS AS CHECAGENS PASSARAM (${#RESULTADOS[@]}/${#RESULTADOS[@]}) ==="
  exit 0
else
  echo "=== $FALHAS CHECAGEM(ENS) FALHARAM de ${#RESULTADOS[@]} ==="
  exit 1
fi
