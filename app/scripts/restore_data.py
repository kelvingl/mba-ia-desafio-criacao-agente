"""Apaga e recria `data/aurora_condo.db` do zero, populado a partir de `dados/*.json`.

Uso: `uv run python -m app.scripts.restore_data`

Não toca em `data/aurora_sessions.db` (sessões do ADK) — ver ADR-08 em
docs/01-decisoes.md. Só conhece `DB_PATH` de `app.db.condo_repo`.
"""

from __future__ import annotations

from app.db import seed as seed_module
from app.db.condo_repo import DB_PATH


def restore() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    seed_module.seed()


if __name__ == "__main__":
    restore()
    print(f"Banco restaurado em {DB_PATH}")
