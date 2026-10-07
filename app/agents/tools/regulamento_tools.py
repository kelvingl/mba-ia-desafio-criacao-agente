"""Tool de consulta ao regulamento, ver T07 (docs/tasks/T07-tools-regulamento.md) e contrato
em docs/03-modelo-dados.md ("Tools expostas aos agentes" / "regulamento/index.py — contrato").

Expõe a busca semântica (RAG) de `app.regulamento.index` como tool de agente. Sem
`tool_context`: o regulamento é igual para todo mundo, não depende do apartamento da sessão.

Garantia 4 (nenhum trecho de capítulo não relacionado entra nos eventos da sessão): esta tool
nunca tem fallback que leia `dados/regulamento.md` inteiro. Se `buscar()` não achar nada
relevante (lista vazia), devolve uma frase curta dizendo isso — nunca o documento completo.
"""

from __future__ import annotations

from app.regulamento import index as regulamento_index

_SEM_RESULTADO = "Não encontrei nada no regulamento sobre esse assunto."


def consultar_regulamento(pergunta: str) -> str:
    """Busca no regulamento do condomínio os trechos mais relevantes para `pergunta`.

    Usa busca semântica (`app.regulamento.index.buscar`) sobre os artigos do regulamento —
    nunca devolve o arquivo inteiro, só os trechos (chunks) mais próximos da pergunta.
    """
    trechos = regulamento_index.buscar(pergunta)

    if not trechos:
        return _SEM_RESULTADO

    return "\n\n---\n\n".join(trechos)
