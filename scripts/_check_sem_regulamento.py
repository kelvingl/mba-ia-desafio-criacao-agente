#!/usr/bin/env python3
"""Checa que `app/agents/root_agent.py` não contém trechos do regulamento.

Garantia 4 (ENUNCIADO.md): o agente principal não pode receber o regulamento
nas instruções. Esta checagem gera "shingles" (janelas de N palavras) do
texto real de `dados/regulamento.md` e procura cada um, literalmente, dentro
de `app/agents/root_agent.py`. Zero ocorrências esperadas.

Usado por `scripts/teste_robusto.sh`; sai com código 0 se a checagem passar,
1 se encontrar overlap (ou se algum dos arquivos não existir).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_AGENT = REPO_ROOT / "app" / "agents" / "root_agent.py"
REGULAMENTO = REPO_ROOT / "dados" / "regulamento.md"
JANELA = 8  # palavras por shingle -- curto o bastante pra pegar paráfrase óbvia,
            # longo o bastante pra não dar falso positivo com palavras comuns.


def _palavras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def main() -> int:
    if not ROOT_AGENT.exists() or not REGULAMENTO.exists():
        print(f"[erro] arquivo esperado não encontrado: {ROOT_AGENT} ou {REGULAMENTO}", file=sys.stderr)
        return 1

    root_palavras = _palavras(ROOT_AGENT.read_text(encoding="utf-8"))
    root_texto = " ".join(root_palavras)

    reg_palavras = _palavras(REGULAMENTO.read_text(encoding="utf-8"))
    shingles = {
        " ".join(reg_palavras[i : i + JANELA])
        for i in range(0, max(0, len(reg_palavras) - JANELA), 4)
    }

    achados = [s for s in shingles if s and s in root_texto]
    if achados:
        print(f"[FAIL] {len(achados)} trecho(s) do regulamento encontrados em root_agent.py:", file=sys.stderr)
        for s in achados[:5]:
            print(f"  - {s!r}", file=sys.stderr)
        return 1

    print(f"[OK] nenhum dos {len(shingles)} shingles do regulamento aparece em root_agent.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
