-- Schema de data/aurora_condo.db (ver docs/03-modelo-dados.md e ADR-04/ADR-05 em docs/01-decisoes.md).
-- Mantido com o texto EXATO do contrato: quem toca neste arquivo quebra outras tarefas.

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
