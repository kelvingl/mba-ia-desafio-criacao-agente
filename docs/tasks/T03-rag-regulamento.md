# T03 — RAG do regulamento

**Depende de**: T00. **Bloqueia**: T07.

## Objetivo

Permitir responder dúvidas de regulamento citando só o(s) trecho(s) relevante(s) de
`dados/regulamento.md`, sem nunca carregar o arquivo inteiro no histórico da conversa ou nas
instruções de um agente (Garantia 4).

## Passos

1. `app/regulamento/chunker.py`: parseia `dados/regulamento.md` e fatia por capítulo/artigo (usar
   os cabeçalhos `## Capítulo` e/ou marcadores `**Art. Nº**` já presentes no arquivo — ver
   estrutura real do arquivo antes de decidir o nível de granularidade; chunks pequenos demais
   perdem contexto do artigo, grandes demais voltam a carregar capítulo inteiro sem necessidade).
2. `app/regulamento/index.py`:
   - `construir_indice()`: embeda cada chunk com um modelo de embedding Gemini (`google-genai`),
     salva em cache local (`data/regulamento_index.json` ou `.npy` + lista de textos) pra não
     reprocessar a cada boot.
   - `buscar(pergunta, k=2) -> list[str]`: embeda a pergunta, similaridade de cosseno contra os
     chunks cacheados, devolve os `k` textos mais próximos.
3. Decidir e documentar (em `../01-decisoes.md`, atualizando ADR-07 se a abordagem mudar) o nível
   de chunking escolhido e o valor de `k`.

## Entregáveis

- `app/regulamento/chunker.py`, `app/regulamento/index.py`.
- Cache de índice versionado ou gerado em build/boot (decidir; se gerado em boot, documentar o
  custo de startup no README).

## Critério de aceite

- `buscar("Até que horas a piscina funciona aos domingos?")` devolve um chunk que contém o horário
  de fechamento da piscina de domingo (checar contra o texto real de `dados/regulamento.md`).
- Nenhuma chamada de `buscar` devolve o arquivo inteiro nem chunks de capítulos sem relação com a
  pergunta nos top-k retornados para perguntas claramente específicas (teste com 2–3 perguntas de
  assuntos diferentes).
