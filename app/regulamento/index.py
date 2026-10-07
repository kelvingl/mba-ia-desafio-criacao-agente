"""Índice de busca semântica sobre o regulamento (RAG), ver contrato em
docs/03-modelo-dados.md ("regulamento/index.py — contrato") e decisão em ADR-07
(docs/01-decisoes.md).

Fluxo:
    construir_indice() -> embeda cada chunk (gerado por app.regulamento.chunker) com um modelo
    de embedding Gemini e grava um cache em disco (`data/regulamento_index.json`). Idempotente:
    se o cache já existe e o hash do `regulamento.md` não mudou, não reprocessa (nem chama a API).

    buscar(pergunta, k=2) -> embeda a pergunta, calcula similaridade de cosseno em memória contra
    os vetores cacheados (nenhuma biblioteca de vetor dedicada — volume pequeno, ~96 chunks) e
    devolve os k chunks (texto puro) mais próximos. Nunca devolve o arquivo inteiro.

Modelo de embedding: "gemini-embedding-001" (modelo atual de embeddings da API Gemini via
google-genai). Usamos `task_type="RETRIEVAL_DOCUMENT"` para os chunks indexados e
`task_type="RETRIEVAL_QUERY"` para a pergunta — é o par recomendado pela API para RAG
(melhora a similaridade pergunta→trecho em relação a embedar os dois sem task_type).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from google import genai
from google.genai import types

from app.regulamento.chunker import REGULAMENTO_PATH, gerar_chunks

_REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = _REPO_ROOT / "data" / "regulamento_index.json"
EMBEDDING_MODEL = "gemini-embedding-001"

_cliente: genai.Client | None = None


def _obter_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        # python-dotenv já deve ter carregado o .env no startup da app (ver app principal);
        # carregamos aqui também pra este módulo funcionar isoladamente (ex. scripts/testes).
        try:
            from dotenv import load_dotenv

            load_dotenv(_REPO_ROOT / ".env")
        except ImportError:
            pass
        _cliente = genai.Client()
    return _cliente


def _hash_arquivo(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _embedar(textos: list[str], task_type: str) -> list[list[float]]:
    cliente = _obter_cliente()
    resposta = cliente.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=textos,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [list(e.values) for e in resposta.embeddings]


def _indice_atualizado(cache: dict) -> bool:
    if cache.get("source_hash") != _hash_arquivo(REGULAMENTO_PATH):
        return False
    if cache.get("model") != EMBEDDING_MODEL:
        return False
    chunks = cache.get("chunks") or []
    embeddings = cache.get("embeddings") or []
    if not chunks or len(chunks) != len(embeddings):
        return False
    return True


def _carregar_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def construir_indice() -> None:
    """Fateia dados/regulamento.md, embeda, grava cache em disco. Idempotente.

    Não reprocessa (e não chama a API de embeddings) se o cache em `data/regulamento_index.json`
    já existe, foi gerado com o mesmo modelo e o conteúdo de `regulamento.md` não mudou desde
    então (comparação por hash sha256 do arquivo fonte).
    """
    cache_existente = _carregar_cache()
    if cache_existente is not None and _indice_atualizado(cache_existente):
        return

    chunks = gerar_chunks()
    embeddings = _embedar(chunks, task_type="RETRIEVAL_DOCUMENT")

    cache = {
        "model": EMBEDDING_MODEL,
        "source_hash": _hash_arquivo(REGULAMENTO_PATH),
        "chunks": chunks,
        "embeddings": embeddings,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _similaridade_cosseno(a: list[float], b: list[float]) -> float:
    produto = sum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return produto / (norma_a * norma_b)


def buscar(pergunta: str, k: int = 2) -> list[str]:
    """Devolve até k trechos (texto puro do chunk), por similaridade semântica."""
    construir_indice()
    cache = _carregar_cache()
    if cache is None:
        return []

    chunks: list[str] = cache["chunks"]
    embeddings: list[list[float]] = cache["embeddings"]

    (embedding_pergunta,) = _embedar([pergunta], task_type="RETRIEVAL_QUERY")

    pontuados = sorted(
        zip(chunks, embeddings),
        key=lambda par: _similaridade_cosseno(embedding_pergunta, par[1]),
        reverse=True,
    )

    return [texto for texto, _ in pontuados[:k]]


if __name__ == "__main__":
    import sys

    pergunta = sys.argv[1] if len(sys.argv) > 1 else "Até que horas a piscina funciona aos domingos?"
    for trecho in buscar(pergunta):
        print("-" * 40)
        print(trecho)
