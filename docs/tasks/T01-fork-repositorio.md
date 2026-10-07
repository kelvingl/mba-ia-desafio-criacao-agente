# T01 — Fork público + remoto

**Depende de**: nada (pode ser feito em qualquer momento, inclusive antes de T00). **Bloqueia**:
entrega final (não bloqueia nenhuma tarefa de código).

## Objetivo

Ter um fork público de `devfullcycle/mba-ia-desafio-criacao-agente` na conta GitHub do usuário, com
este repositório apontando pra ele, porque o entregável final é "link do fork público ... com tudo
na branch `main`".

## Situação atual (checada em 2026-10-07)

`git remote -v` mostra `origin` apontando para
`git@github.com:devfullcycle/mba-ia-desafio-criacao-agente.git` (o repo-base, não um fork do
usuário) — precisa trocar.

## Passos

1. No GitHub, fazer fork de `devfullcycle/mba-ia-desafio-criacao-agente` para a conta do usuário
   (`kelvin_gl` ou equivalente), mantendo público.
2. Neste clone local:
   ```
   git remote set-url origin git@github.com:<usuario>/mba-ia-desafio-criacao-agente.git
   # ou renomear o atual para upstream e adicionar um novo origin, como preferir
   ```
3. Confirmar que o push de trabalho vai pra `main` do fork, não pro repo-base (checar
   `git remote -v` de novo e fazer um push de teste).

## Critério de aceite

- `git remote -v` mostra `origin` apontando pro fork do usuário.
- Fork visível publicamente no GitHub.
- Branch `main` do fork recebe os commits deste trabalho.
