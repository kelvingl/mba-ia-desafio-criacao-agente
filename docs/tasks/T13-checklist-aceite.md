# T13 — Checklist final de aceite

**Depende de**: T11. **Bloqueia**: entrega (push final na `main` do fork).

## Objetivo

Passar item a item pela seção "Critérios de aceite" do `ENUNCIADO.md` antes de considerar o
desafio entregue, com evidência concreta de cada um (não "deveria estar ok" — rodar e checar).

## Checklist (copiado e organizado do `ENUNCIADO.md`, seção "Critérios de aceite")

### Execução e entrega
- [ ] `uv sync` instala sem erro; ADK na série 2, ≥2.2.0, versão exata fixada.
- [ ] Comandos do README deixam a API em `http://localhost:8000` com dados iniciais.
- [ ] `dados/` idêntico ao repositório base (`git diff` contra o commit original de `dados/`).
- [ ] Nenhuma chave versionada; `.env` fora do git; `.env.example` completo.

### Arquitetura
- [ ] Agente principal + ao menos 2 especialistas.
- [ ] Reservas/visitantes só via tool; mudanças da conversa aparecem nas rotas de verificação.

### Garantia 1
- [ ] Reservar área com taxa gera confirmação com área+data em `detalhes`; nada grava antes.
- [ ] Negar não grava nada.
- [ ] Aprovar grava exatamente uma reserva.
- [ ] Reenviar resposta já respondida → `409`, sem reexecutar.
- [ ] `id` não pendente → `409`, sem alterar nada.
- [ ] Área sem taxa não gera confirmação.
- [ ] Autorizar visitante sempre gera confirmação, mesmo com "já confirmei" no texto.

### Garantia 2
- [ ] Pedir dados do 302 numa sessão do 101 não traz `RSV-4821`/`Marina Duarte`.
- [ ] Cancelamento da reserva do 302 numa sessão do 101 não altera nada do 302.
- [ ] Morador cancela a própria reserva sem confirmação.
- [ ] Reservar data já ocupada pelo 302 não cria reserva nem vaza `RSV-4821`/`302`.
- [ ] Apartamento usado pelas tools vem da sessão; nenhuma tool aceita apartamento do modelo.

### Garantia 3
- [ ] Depois de restart, sessão devolve os mesmos eventos e aceita novas mensagens.
- [ ] Reservas/cancelamentos/visitantes de antes do restart continuam valendo; códigos não
      repetem.

### Garantia 4
- [ ] Resposta sobre piscina domingo traz o horário certo.
- [ ] Eventos da sessão incluem chamadas de tool e nenhum trecho de capítulo não relacionado.
- [ ] Agente principal sem o regulamento nas instruções.

### Garantia 5
- [ ] Duas aprovações simultâneas pra mesma área/data respondem `200` as duas.
- [ ] Depois da disputa, soma de reservas entre os dois apartamentos é exatamente 1.
- [ ] Exclusividade garantida no instante da gravação (não só numa checagem prévia).

### Contrato e README
- [ ] Todas as rotas seguem o contrato (caminhos, campos, formatos, status).
- [ ] README com as três seções exigidas, Garantias apontando arquivos/trechos reais.

## Ao concluir

- Push final na `main` do fork (`T01`).
- Conferir que o link do fork está público e acessível sem login.
