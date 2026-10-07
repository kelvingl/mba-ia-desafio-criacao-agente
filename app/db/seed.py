"""Popula `data/aurora_condo.db` do zero a partir de `dados/*.json`.

`dados/apartamentos.json` e `dados/areas.json` NÃO têm tabela própria no contrato
(`docs/03-modelo-dados.md`) — `obter_area` lê `areas.json` direto (em memória).
Aqui eles servem só para validar que `reservas.json`/`visitantes.json` referenciam
apartamentos/áreas existentes antes de gravar.

Idempotente: sempre limpa `reservas`, `visitantes` e `confirmacoes` antes de inserir
(chamado por `app/scripts/restore_data.py`, que já recria o arquivo do banco do zero).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.db.condo_repo import DB_PATH, get_connection

BASE_DIR = Path(__file__).resolve().parents[2]
DADOS_DIR = BASE_DIR / "dados"


def _load_json(nome: str) -> list[dict]:
    with open(DADOS_DIR / nome, encoding="utf-8") as f:
        return json.load(f)


def _numero_codigo(codigo: str) -> int:
    """Extrai o inteiro de 'RSV-1377' -> 1377. 0 se não reconhecer o padrão."""
    try:
        return int(codigo.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        return 0


def seed() -> None:
    apartamentos = _load_json("apartamentos.json")
    areas = _load_json("areas.json")
    reservas = _load_json("reservas.json")
    visitantes = _load_json("visitantes.json")

    apartamentos_validos = {a["numero"] for a in apartamentos}
    areas_validas = {a["id"] for a in areas}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM reservas")
        conn.execute("DELETE FROM visitantes")
        conn.execute("DELETE FROM confirmacoes")
        conn.execute(
            "INSERT OR IGNORE INTO contador_reserva (id, valor) VALUES (1, 0)"
        )
        conn.execute("UPDATE contador_reserva SET valor = 0 WHERE id = 1")

        maior_contador = 0
        for r in reservas:
            if r["apartamento"] not in apartamentos_validos:
                raise ValueError(
                    f"seed: apartamento '{r['apartamento']}' em reservas.json não existe"
                    " em apartamentos.json"
                )
            if r["area"] not in areas_validas:
                raise ValueError(
                    f"seed: area '{r['area']}' em reservas.json não existe em areas.json"
                )
            conn.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data, status)"
                " VALUES (?, ?, ?, ?, 'ativa')",
                (r["codigo"], r["apartamento"], r["area"], r["data"]),
            )
            maior_contador = max(maior_contador, _numero_codigo(r["codigo"]))

        for v in visitantes:
            if v["apartamento"] not in apartamentos_validos:
                raise ValueError(
                    f"seed: apartamento '{v['apartamento']}' em visitantes.json não"
                    " existe em apartamentos.json"
                )
            conn.execute(
                "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
                (v["apartamento"], v["nome"], v["data"]),
            )

        # Contador começa no maior código já seedado, pra nunca colidir com um
        # código existente (mesmo que a reserva seedada seja cancelada depois) —
        # ver ADR-05.
        conn.execute(
            "UPDATE contador_reserva SET valor = ? WHERE id = 1", (maior_contador,)
        )
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
    print(f"Seed concluído em {DB_PATH}")
