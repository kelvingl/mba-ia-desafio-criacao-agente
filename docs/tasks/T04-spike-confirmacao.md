# T04 — Spike: confirmação de tool + resume + sessão persistida

**Depende de**: T00. **Bloqueia**: T08, T09 (BLOQUEANTE — ver `../05-riscos.md` R1).

## Objetivo

Provar, num protótipo isolado e descartável, que o fluxo "tool pede confirmação → cliente responde
→ execução retoma" funciona com `DatabaseSessionService` (SQLite) **e sobrevive a um restart do
processo no meio**, antes de qualquer outra tarefa depender disso.

Este é o ponto que o próprio enunciado chama de "a armadilha mais cara": a rota de confirmação
responde `200` sem erro, mas a ação nunca executa, porque a resposta não chegou ao agente que
pediu a confirmação. A causa depende de topologia de agentes, bloqueios de transferência,
configuração de retomada do `App` e serviço de sessão — não dá pra adivinhar, tem que testar.

## Passos

1. Criar um script solto em `app/scripts/spike_confirmacao.py` (ou pasta temporária, não precisa
   ser definitivo) com:
   - Um único agente (não precisa dos 3 especialistas ainda) com uma tool simples marcada para
     exigir confirmação (mecanismo nativo do ADK — consultar documentação oficial de "confirmação
     de ações" e, se necessário, o código-fonte do pacote instalado via
     `uv run python -c "import google.adk; print(google.adk.__file__)"`).
   - `DatabaseSessionService` apontando pra um arquivo SQLite real (não em memória).
   - Um `Runner`/`App` chamando o agente.
2. Rodar o fluxo: enviar mensagem que aciona a tool → capturar o evento de confirmação pendente →
   construir a resposta de confirmação (conferir no ADK qual o formato exato esperado para
   retomar) → enviar e confirmar que a tool executou.
3. **Matar o processo** (`Ctrl+C` de verdade, ou encerrar o script) depois do passo 2 gerar a
   pendência, **antes** de responder a confirmação. Rodar um segundo processo que carrega a mesma
   sessão do mesmo arquivo SQLite e envia a resposta de confirmação. Confirmar que ainda funciona.
4. Testar pelo menos duas topologias diferentes se a primeira falhar no passo 3:
   - Especialista acionado via `sub_agents` (transfer automático do LLM).
   - Especialista acionado via `AgentTool` (agente como tool, pai permanece "ativo").
   Registrar qual funcionou e por quê em `../01-decisoes.md` (atualizar ADR-02/ADR-06 se a escolha
   de topologia mudar por causa disso).
5. Apagar ou mover o script de spike para fora de `app/` depois de documentar a conclusão (não é
   parte do produto final, é só para destravar a decisão).

## Entregáveis

- Conclusão documentada em `../01-decisoes.md`: qual topologia de agentes e qual configuração de
  `App`/Runner garantem retomada correta com sessão persistida e com restart no meio.
- Se algo no ADK exigir uma configuração específica (ex.: desabilitar um tipo de transferência,
  usar um parâmetro de resume do `App`), documentar exatamente qual e por quê — isso vai direto
  pra `T08`/`T09`.

## Critério de aceite

- Fluxo completo (pedir confirmação → matar processo → novo processo → responder confirmação →
  tool executa) funciona de ponta a ponta pelo menos uma vez, de forma reproduzível.
- A versão exata do ADK usada no spike é a que vai pro `pyproject.toml` definitivo (não trocar
  depois sem re-rodar o spike — ver R6 em `../05-riscos.md`).
