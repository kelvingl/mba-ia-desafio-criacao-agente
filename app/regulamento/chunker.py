"""Fatiamento de `dados/regulamento.md` em chunks pequenos e autocontidos.

Decisão de granularidade (ver ADR-07 em docs/01-decisoes.md): um chunk por **artigo**
(`**Art. Nº**` ... até o próximo artigo ou capítulo), prefixado com o título do capítulo a que
pertence.

Por quê artigo, e não capítulo: capítulos deste regulamento têm de 1 a ~18 artigos (ex.
Capítulo XIII tem 5 artigos de penalidades; Capítulo IV — Piscina tem 8 artigos). Um chunk por
capítulo devolveria, pra uma pergunta pontual como "até que horas a piscina funciona aos
domingos", o capítulo inteiro (regras de exame dermatológico, crianças, proibições, etc.) —
voltando a carregar texto irrelevante no contexto do agente, o que a Garantia 4 proíbe. Um chunk
por artigo isolado, sem o título do capítulo, perderia o contexto temático (ex. "Art. 22" sem
saber que é sobre a piscina). Por isso cada chunk = cabeçalho do capítulo + texto completo do
artigo (incluindo seus parágrafos e incisos, que não têm marcador próprio e ficam coesos com o
artigo a que pertencem).
"""

from __future__ import annotations

import re
from pathlib import Path

REGULAMENTO_PATH = Path(__file__).resolve().parents[2] / "dados" / "regulamento.md"

_CAPITULO_RE = re.compile(r"^##\s+(.+)$")
_ARTIGO_RE = re.compile(r"^\*\*Art\.\s*\d+")


def _ler_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def gerar_chunks(caminho: Path | None = None) -> list[str]:
    """Parseia o regulamento e devolve uma lista de chunks (texto puro).

    Cada chunk = "<título do capítulo>\n\n<texto do artigo, com parágrafos e incisos>".
    Linhas antes do primeiro "**Art." dentro de um capítulo (se houver) ficam acopladas ao
    primeiro artigo seguinte, pra nenhum texto do documento ser descartado.
    """
    caminho = caminho or REGULAMENTO_PATH
    texto = _ler_texto(caminho)

    capitulo_atual: str | None = None
    artigo_linhas: list[str] = []
    chunks: list[str] = []

    def _fechar_artigo() -> None:
        if artigo_linhas and any(linha.strip() for linha in artigo_linhas):
            corpo = "\n".join(artigo_linhas).strip()
            if capitulo_atual:
                chunks.append(f"{capitulo_atual}\n\n{corpo}")
            else:
                chunks.append(corpo)
        artigo_linhas.clear()

    for linha_bruta in texto.splitlines():
        linha = linha_bruta.rstrip()

        if linha.startswith("# "):
            # título do documento — não faz parte de nenhum chunk
            continue

        m_cap = _CAPITULO_RE.match(linha)
        if m_cap:
            _fechar_artigo()
            capitulo_atual = m_cap.group(1).strip()
            continue

        if _ARTIGO_RE.match(linha):
            _fechar_artigo()
            artigo_linhas.append(linha)
            continue

        artigo_linhas.append(linha)

    _fechar_artigo()

    return chunks


if __name__ == "__main__":
    chunks = gerar_chunks()
    print(f"{len(chunks)} chunks gerados.")
    for c in chunks[:3]:
        print("-" * 40)
        print(c)
