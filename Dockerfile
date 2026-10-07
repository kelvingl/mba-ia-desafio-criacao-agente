# Imagem de execução/teste da API do Residencial Aurora.
#
# Não é exigida pelo enunciado (storage é SQLite em arquivo, sem serviço
# externo) — existe só para dar ao script de teste robusto
# (scripts/teste_robusto.sh) um ambiente limpo e reproduzível, equivalente a
# "clone limpo + uv sync + comando de subida" do passo 1 do fluxo do
# avaliador, sem depender do estado da máquina de quem roda o teste.
FROM python:3.12-slim AS base

# Binário oficial do uv, copiado direto da imagem distroless deles — evita
# baixar/rodar o install script dentro do build (mais robusto e mais rápido
# em builds repetidos, com cache de camada).
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /usr/local/bin/

WORKDIR /app

# Camada de dependências isolada do código: só invalida se pyproject/uv.lock
# mudarem, não a cada edição de app/.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Código e dados do condomínio (dados/ é somente leitura em runtime — o
# estado mutável vive em data/, montado como volume pelo compose).
COPY app ./app
COPY dados ./dados

RUN uv sync --frozen

# Roda como usuário não-root com UID/GID 1000 (o padrão em praticamente
# toda distro Linux de desenvolvedor, incluindo esta) -- sem isso, os
# arquivos que a API cria em data/ (bind mount) ficam donos de `root` no
# host, e o dev não consegue mais ler/apagar sem sudo. Criar o diretório
# ANTES de trocar de usuário garante que o ponto de montagem já exista com
# o dono certo mesmo antes do primeiro `docker compose up`.
RUN groupadd -g 1000 aurora && useradd -u 1000 -g aurora -m aurora \
    && mkdir -p /app/data && chown -R aurora:aurora /app
USER aurora

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
