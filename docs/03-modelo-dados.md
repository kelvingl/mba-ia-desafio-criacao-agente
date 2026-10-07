# Contratos de dados e de função

Estes contratos existem para que tarefas diferentes (ver `tasks/`) possam ser feitas em paralelo
sem esperar a implementação completa umas das outras — quem constrói as tools ou os agentes
programa contra esta interface, não contra o código interno de `condo_repo.py`.
**Mudar uma assinatura aqui exige atualizar quem depende dela.**

## `data/aurora_condo.db` — schema

```sql
CREATE TABLE reservas (
    codigo      TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    area        TEXT NOT NULL,
    data        TEXT NOT NULL,   -- AAAA-MM-DD
    status      TEXT NOT NULL CHECK (status IN ('ativa', 'cancelada'))
);
CREATE UNIQUE INDEX uq_reserva_ativa ON reservas(area, data) WHERE status = 'ativa';

CREATE TABLE visitantes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome        TEXT NOT NULL,
    data        TEXT NOT NULL   -- AAAA-MM-DD
);

CREATE TABLE confirmacoes (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    acao        TEXT NOT NULL,          -- ex.: "criar_reserva", "autorizar_visitante"
    detalhes    TEXT NOT NULL,          -- JSON com os campos que vão em `detalhes` na API
    status      TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied')),
    criado_em   TEXT NOT NULL
);

CREATE TABLE contador_reserva (
    id     INTEGER PRIMARY KEY CHECK (id = 1),
    valor  INTEGER NOT NULL
);
```

Seed inicial (via `scripts/restore_data.py`) vem de `dados/apartamentos.json`, `dados/areas.json`,
`dados/reservas.json`, `dados/visitantes.json` — lidos, nunca alterados.

## `app/db/condo_repo.py` — funções expostas

Todas síncronas, cada uma abre sua própria transação (nenhuma assume transação externa aberta).

```python
def listar_reservas(apartamento: str) -> list[dict]:
    """[{"codigo": str, "area": str, "data": str}], só reservas status='ativa'."""

def listar_visitantes(apartamento: str) -> list[dict]:
    """[{"nome": str, "data": str}]."""

def consultar_disponibilidade(area: str, data: str) -> bool:
    """True = livre, False = ocupada. Nunca devolve apartamento/código."""

def criar_reserva(apartamento: str, area: str, data: str) -> dict:
    """
    Tenta INSERT atômico (BEGIN IMMEDIATE) respeitando uq_reserva_ativa.
    Retorno: {"ok": True, "codigo": str} ou {"ok": False, "motivo": "ocupada"}.
    NUNCA lança exceção de integridade para fora — captura e devolve "ocupada".
    """

def cancelar_reserva(apartamento: str, codigo: str) -> dict:
    """
    Só cancela reserva cujo `apartamento` bate com o parâmetro (defesa em profundidade;
    quem chama já deve ter vindo do apartamento da sessão).
    Retorno: {"ok": True} ou {"ok": False, "motivo": "nao_encontrada"}.
    """

def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict:
    """Retorno: {"ok": True}."""

def obter_area(area_id: str) -> dict | None:
    """{"id", "nome", "taxa"} a partir de dados/areas.json carregado em memória/tabela."""

def criar_confirmacao(session_id: str, acao: str, detalhes: dict) -> str:
    """Gera id novo, grava status='pending', devolve o id."""

def responder_confirmacao(session_id: str, confirmacao_id: str, confirmado: bool) -> dict:
    """
    Atômico: só transiciona se status atual == 'pending' E session_id bate.
    Retorno: {"ok": True, "detalhes": {...}, "acao": str} ou {"ok": False} (→ API devolve 409).
    """

def listar_confirmacoes_pendentes(session_id: str) -> list[dict]:
    """[{"id", "acao", "detalhes"}] com status='pending', para a sessão."""
```

**Regra de ouro desta camada**: nenhuma função aqui recebe "qual agente pediu" nem lê nada do
prompt — só parâmetros de domínio. Quem garante que `apartamento` veio da sessão (não do modelo)
é a camada de tools (ver `tasks/T05`, `T06`), não esta.

## Tools expostas aos agentes (assinatura vista pelo modelo)

As tools **não têm parâmetro `apartamento`** — ele é injetado via `tool_context.state["apartamento"]`
dentro da implementação, nunca aparece no schema que o modelo vê.

```python
def consultar_disponibilidade(area: str, data: str) -> str: ...
def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict: ...   # require_confirmation se taxa>0
def cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict: ...
def listar_minhas_reservas(tool_context: ToolContext) -> list[dict]: ...

def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict: ...  # require_confirmation sempre
def listar_meus_visitantes(tool_context: ToolContext) -> list[dict]: ...

def consultar_regulamento(pergunta: str) -> str: ...
```

## `regulamento/index.py` — contrato

```python
def construir_indice() -> None:
    """Fateia dados/regulamento.md, embeda, grava cache em disco. Idempotente."""

def buscar(pergunta: str, k: int = 2) -> list[str]:
    """Devolve até k trechos (texto puro do chunk), por similaridade semântica."""
```

## Resposta HTTP — formato comum (`mensagens` e `confirmacoes`)

```json
{
  "resposta": "string (pode ser vazia)",
  "confirmacoes_pendentes": [
    {"id": "string", "acao": "string", "detalhes": {"...": "..."}}
  ]
}
```

`detalhes` para `reservar_area` → `{"area": "<id>", "data": "AAAA-MM-DD"}`.
`detalhes` para `autorizar_visitante` → `{"nome": "<string>", "data": "AAAA-MM-DD"}`.
