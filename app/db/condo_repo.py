"""Camada de acesso a `data/aurora_condo.db`.

Contrato exato em `docs/03-modelo-dados.md` (seção
"`app/db/condo_repo.py` — funções expostas"). Outras tarefas programam contra estas
assinaturas — não mudar nomes/retornos sem atualizar o contrato e quem depende dele.

Regra de ouro (ver docs/03-modelo-dados.md): nenhuma função aqui recebe "qual agente
pediu" nem lê nada de prompt — só parâmetros de domínio explícitos. Garantir que
`apartamento` vem da sessão (não do modelo) é responsabilidade da camada de tools.

Nenhuma função propaga exceção para um caminho de negócio esperado (área ocupada,
confirmação já respondida/inexistente, reserva não encontrada) — tudo volta como dict.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "aurora_condo.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
AREAS_PATH = BASE_DIR / "dados" / "areas.json"

# Timeout de espera por lock do SQLite quando duas transações `BEGIN IMMEDIATE`
# concorrem pela mesma escrita — sem isso a segunda falharia com "database is
# locked" (OperationalError) em vez de esperar sua vez e cair no IntegrityError
# esperado do índice único (ADR-04).
_BUSY_TIMEOUT_MS = 5000

_areas_cache: list[dict] | None = None


def get_connection() -> sqlite3.Connection:
    """Abre uma conexão nova, garante schema+dados mínimos e devolve pronta pra uso.

    `isolation_level=None` (modo autocommit do driver) para controlarmos `BEGIN
    IMMEDIATE`/`COMMIT`/`ROLLBACK` manualmente onde a transação precisa abranger
    mais de um statement (ver `criar_reserva`, `responder_confirmacao`).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Cria tabelas/índice do schema.sql se ainda não existirem (idempotente).

    `schema.sql` é mantido com o DDL exato do contrato (sem `IF NOT EXISTS`), então a
    idempotência é feita aqui: cada statement é tentado e um erro de "já existe" é
    ignorado.
    """
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    for statement in filter(None, (s.strip() for s in script.split(";"))):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc):
                raise
    conn.execute(
        "INSERT OR IGNORE INTO contador_reserva (id, valor) VALUES (1, 0)"
    )


def _load_areas() -> list[dict]:
    global _areas_cache
    if _areas_cache is None:
        with open(AREAS_PATH, encoding="utf-8") as f:
            _areas_cache = json.load(f)
    return _areas_cache


def listar_reservas(apartamento: str) -> list[dict]:
    """[{"codigo": str, "area": str, "data": str}], só reservas status='ativa'."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND status = 'ativa'"
            " ORDER BY data",
            (apartamento,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_visitantes(apartamento: str) -> list[dict]:
    """[{"nome": str, "data": str}]."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data",
            (apartamento,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def consultar_disponibilidade(area: str, data: str) -> bool:
    """True = livre, False = ocupada. Nunca devolve apartamento/código."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa'",
            (area, data),
        ).fetchone()
        return row is None
    finally:
        conn.close()


def criar_reserva(apartamento: str, area: str, data: str) -> dict:
    """
    Tenta INSERT atômico (BEGIN IMMEDIATE) respeitando uq_reserva_ativa.
    Retorno: {"ok": True, "codigo": str} ou {"ok": False, "motivo": "ocupada"}.
    NUNCA lança exceção de integridade para fora — captura e devolve "ocupada".
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT valor FROM contador_reserva WHERE id = 1"
            ).fetchone()
            novo_valor = (row["valor"] if row else 0) + 1
            codigo = f"RSV-{novo_valor}"
            conn.execute(
                "UPDATE contador_reserva SET valor = ? WHERE id = 1", (novo_valor,)
            )
            conn.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data, status)"
                " VALUES (?, ?, ?, ?, 'ativa')",
                (codigo, apartamento, area, data),
            )
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return {"ok": False, "motivo": "ocupada"}
        conn.execute("COMMIT")
        return {"ok": True, "codigo": codigo}
    finally:
        conn.close()


def cancelar_reserva(apartamento: str, codigo: str) -> dict:
    """
    Só cancela reserva cujo `apartamento` bate com o parâmetro (defesa em
    profundidade; quem chama já deve ter vindo do apartamento da sessão).
    Retorno: {"ok": True} ou {"ok": False, "motivo": "nao_encontrada"}.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE reservas SET status = 'cancelada'"
            " WHERE codigo = ? AND apartamento = ? AND status = 'ativa'",
            (codigo, apartamento),
        )
        if cur.rowcount == 0:
            return {"ok": False, "motivo": "nao_encontrada"}
        return {"ok": True}
    finally:
        conn.close()


def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict:
    """Retorno: {"ok": True}."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )
        return {"ok": True}
    finally:
        conn.close()


def obter_area(area_id: str) -> dict | None:
    """{"id", "nome", "taxa"} a partir de dados/areas.json carregado em memória."""
    for area in _load_areas():
        if area["id"] == area_id:
            return {"id": area["id"], "nome": area["nome"], "taxa": area["taxa"]}
    return None


def criar_confirmacao(session_id: str, acao: str, detalhes: dict) -> str:
    """Gera id novo, grava status='pending', devolve o id."""
    conn = get_connection()
    try:
        confirmacao_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO confirmacoes (id, session_id, acao, detalhes, status, criado_em)"
            " VALUES (?, ?, ?, ?, 'pending', ?)",
            (
                confirmacao_id,
                session_id,
                acao,
                json.dumps(detalhes),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return confirmacao_id
    finally:
        conn.close()


def responder_confirmacao(
    session_id: str, confirmacao_id: str, confirmado: bool
) -> dict:
    """
    Atômico: só transiciona se status atual == 'pending' E session_id bate.
    Retorno: {"ok": True, "detalhes": {...}, "acao": str} ou {"ok": False} (→ API
    devolve 409).
    """
    novo_status = "approved" if confirmado else "denied"
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE confirmacoes SET status = ?"
            " WHERE id = ? AND session_id = ? AND status = 'pending'",
            (novo_status, confirmacao_id, session_id),
        )
        if cur.rowcount == 0:
            conn.execute("ROLLBACK")
            return {"ok": False}
        row = conn.execute(
            "SELECT acao, detalhes FROM confirmacoes WHERE id = ?",
            (confirmacao_id,),
        ).fetchone()
        conn.execute("COMMIT")
        return {"ok": True, "detalhes": json.loads(row["detalhes"]), "acao": row["acao"]}
    finally:
        conn.close()


def listar_confirmacoes_pendentes(session_id: str) -> list[dict]:
    """[{"id", "acao", "detalhes"}] com status='pending', para a sessão."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, acao, detalhes FROM confirmacoes"
            " WHERE session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchall()
        return [
            {"id": r["id"], "acao": r["acao"], "detalhes": json.loads(r["detalhes"])}
            for r in rows
        ]
    finally:
        conn.close()
