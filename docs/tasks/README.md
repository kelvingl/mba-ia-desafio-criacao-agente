# Backlog de tarefas

Cada tarefa é um arquivo autocontido: objetivo, dependências, contratos de entrada/saída (ligados a
[`../03-modelo-dados.md`](../03-modelo-dados.md)), entregáveis e critérios de aceite. Pensado para
que agentes/sessões diferentes peguem tarefas em paralelo sem precisar da conversa inteira — cada
arquivo tem o contexto que basta.

## Grafo de dependências

```
T00 (setup projeto)
 ├─▶ T01 (fork — independente, pode rodar em qualquer momento)
 ├─▶ T02 (dados condomínio: schema, repo, seed, restore)
 ├─▶ T03 (RAG regulamento: chunker, índice, busca)
 └─▶ T04 (spike confirmação+resume+persistência) ── BLOQUEANTE pra T08/T09

T02 ─▶ T05 (tools reservas)
T02 ─▶ T06 (tools visitantes)
T03 ─▶ T07 (tools regulamento)

T04 + T05 + T06 + T07 ─▶ T08 (agentes: root + 3 especialistas)
T04 + T08 ─▶ T09 (Runner/App + fluxo de confirmação + tabela confirmacoes)
T02 + T09 ─▶ T10 (rotas FastAPI, contrato completo)
T10 ─▶ T11 (teste automatizado do fluxo do avaliador)
T11 ─▶ T13 (checklist final de aceite)

T12 (README) ─ pode começar em paralelo com qualquer coisa (rascunho), mas só fecha depois de
               T08/T09/T02/T03 estarem com arquivo+trecho reais para citar.
```

## Grupos paralelizáveis

- **Onda 1** (após T00): `T01`, `T02`, `T03`, `T04` — zero dependência entre si, podem ser 4
  sessões/agentes diferentes simultaneamente.
- **Onda 2**: `T05` e `T06` (ambos só dependem de T02, podem ser paralelos entre si) e `T07`
  (depende só de T03).
- **Onda 3**: `T08` (precisa de T04 decidido + T05/T06/T07 prontos).
- **Onda 4**: `T09` → `T10` → `T11` → `T13` (sequenciais, cada uma depende da anterior).
- **Contínuo**: `T12` (README) evolui em paralelo a tudo, fecha por último.

## Lista

| ID | Título | Depende de |
|---|---|---|
| [T00](T00-setup-projeto.md) | Setup do projeto (uv, deps, .env) | — |
| [T01](T01-fork-repositorio.md) | Fork público + remoto | — |
| [T02](T02-dados-condominio.md) | Schema + repo de dados do condomínio | T00 |
| [T03](T03-rag-regulamento.md) | RAG do regulamento | T00 |
| [T04](T04-spike-confirmacao.md) | Spike: confirmação + resume + sessão persistida | T00 |
| [T05](T05-tools-reservas.md) | Tools de reservas | T02 |
| [T06](T06-tools-visitantes.md) | Tools de visitantes | T02 |
| [T07](T07-tools-regulamento.md) | Tool de consulta ao regulamento | T03 |
| [T08](T08-agentes-adk.md) | Agentes ADK (root + especialistas) | T04, T05, T06, T07 |
| [T09](T09-runner-confirmacoes.md) | Runner/App + fluxo HTTP de confirmação | T04, T08 |
| [T10](T10-api-fastapi.md) | Rotas FastAPI completas | T02, T09 |
| [T11](T11-teste-fluxo-avaliador.md) | Teste automatizado do fluxo do avaliador | T10 |
| [T12](T12-readme.md) | README final (Arquitetura, Garantias, Como rodar) | contínuo, fecha após T02/T03/T08/T09 |
| [T13](T13-checklist-aceite.md) | Checklist final de aceite | T11 |
