# Plano de testes

Base: seção "Fluxo do avaliador" do `ENUNCIADO.md` (passos 1 a 15) e "Critérios de aceite". A
tarefa `tasks/T11-teste-fluxo-avaliador.md` entrega um script que automatiza os passos 1–14 via
HTTP (os únicos verificáveis por chamadas de API) e documenta como checar manualmente o passo 15
(inspeção de repositório).

## Por que automatizar

Os passos 1–14 são determinísticos e verificáveis por request/response — dá pra rodar como teste
de integração real contra a API de pé, sem mock de nada. Isso pega regressão de qualquer tarefa
(`T05` a `T10`) antes da entrega.

## Casos que precisam de atenção especial (não são só "happy path")

- **Passo 3/4/10**: precisam inspecionar não só `resposta`, mas também `GET /sessoes/{id}/eventos`
  procurando literalmente pelas strings `RSV-4821`, `Marina Duarte`, e o número `302` isolado.
- **Passo 8**: reenviar a mesma confirmação já respondida → `409`, e checar que a contagem de
  reservas do 101 pro salão em `2030-04-20` continua em exatamente 1 (não 0, não 2).
- **Passo 9**: `id` inexistente → `409`; sessão inexistente em `GET /eventos` → `404`.
- **Passo 12**: checar o conteúdo da resposta contra o regulamento real (horário de fechamento da
  piscina domingo) E inspecionar eventos em busca de trechos de capítulos não relacionados à
  pergunta. Anotar a contagem de eventos pro passo 13.
- **Passo 13**: matar o processo da API (`Ctrl+C`/`SIGINT`, não `kill -9` destrutivo de mais),
  subir de novo com o mesmo comando, sem restore, e comparar contagem de eventos antes/depois.
- **Passo 14**: dois `curl`/requests disparados concorrentemente (de fato em paralelo, não
  sequenciais com `await` um atrás do outro) contra duas sessões diferentes; checar que a soma de
  reservas do salão em `2030-05-11` entre os apartamentos 101 e 201 é exatamente 1.

## Passo 15 (inspeção manual de repositório) — checklist

- [ ] Versão exata do ADK no `pyproject.toml`/`uv.lock`, série 2, ≥2.2.0.
- [ ] `dados/*.json` e `dados/regulamento.md` idênticos aos do repositório base (`git diff` contra
      o commit original).
- [ ] Nenhuma chave versionada; `.env` fora do git; `.env.example` com os nomes das variáveis.
- [ ] Agente principal + pelo menos 2 especialistas, reservas/visitantes só via tool.
- [ ] Nenhuma tool com parâmetro de apartamento escolhido pelo modelo (grep por `apartamento` nas
      assinaturas de tool em `app/agents/tools/`).
- [ ] Agente principal sem o regulamento nas instruções (grep por conteúdo do regulamento fora de
      `app/agents/especialista_regulamento.py` e `app/regulamento/`).
- [ ] Índice único/transação da Garantia 5 presente e exercitado pelo teste de concorrência.
- [ ] README com as três seções exigidas, citando arquivo+trecho reais para cada garantia.

## Onde roda

Script de teste em `scripts/` ou `tests/fluxo_avaliador.py` (decisão de `T11`), execução via
`uv run python scripts/fluxo_avaliador.py` contra a API já de pé em `localhost:8000`. Não substitui
o passo manual 13/15 (restart de processo e inspeção de repositório), que ficam documentados como
checklist manual neste arquivo.
