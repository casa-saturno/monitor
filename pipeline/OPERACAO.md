# Monitor Casa Saturno — operação

Quem faz o quê, o que já quebrou e como voltar atrás. Atualizado em 31/08/2026.

## Quem coleta o quê

| | quem | quando | estado |
|---|---|---|---|
| YouTube | GitHub Actions (`.github/workflows/monitor.yml`), Data API v3 | diário, 12:00 UTC (9h BRT) | automático, não depende de máquina ligada |
| Instagram | rodada de navegador (tarefa agendada, sessão Cowork) | 11h00 e 19h10 BRT | depende do Chrome conectado e logado |
| TikTok | idem | idem, 2 perfis por rodada em rodízio | depende do Chrome; limitado por ritmo |
| Publicação | commit do `index.html` na raiz (GitHub Pages) | a cada rodada | — |

O repositório é a fonte de verdade. A pasta "Monitor Saturno" no OneDrive é espelho
humano (xlsx + painel) e rede de segurança: a rodada grava lá **antes** de tentar
publicar, porque o transporte é o elo fraco, não a coleta.

## Rotina antiga — PAUSADA em 31/08/2026

`trig_011SxESS9DGgXWvQRk9wKyWX` — "[PAUSADA] Monitor Saturno — rotina antiga (navegador)"
Ligada à sessão `session_01EMHyp51ByS7aMrBc7Y2VmM`.

Foi pausada, **não apagada**: o prompt inteiro segue guardado e ela volta a funcionar
com um `update_trigger enabled:true` mais um `run_once_at` no futuro (é one-shot que se
reagenda ao final de cada rodada; sem uma data futura ela não dispara sozinha).

Por que foi pausada: os dois critérios de desligamento que ela mesma definia foram
cumpridos em 31/08 — (a) o Actions publicando a partir do espelho, e (b) uma rodada
fechando o ciclo com Instagram. Rodava em paralelo com a nova havia três dias e as duas
escreviam nos mesmos arquivos com regras diferentes.

O que ela fazia e a nova não faz:
- coletava YouTube por RSS numa aba do navegador (hoje o Actions cobre, pela Data API);
- fazia merge por plataforma entre a base do OneDrive e a do repo;
- atualizava um artifact de desktop (`update_artifact`), descontinuado.

Se precisar dela de volta, atenção: o prompt guardado usa `web_profile_info` para
contadores, e esse endpoint morreu (ver abaixo).

## Armadilhas conhecidas

**`web_profile_info` está morto.** O endpoint `/api/v1/users/web_profile_info/` devolve
400. Foi ele que degradou os contadores para `carry`/`seed` por semanas sem alarme.
O substituto é `/api/v1/users/<uid>/info/` → `user.follower_count`, `user.media_count`.

**Login do Instagram não se detecta por `document.cookie`.** O cookie `sessionid` é
HttpOnly. Testar por ele dá falso negativo — teste chamando o endpoint de feed direto.

**TikTok não está bloqueado, é lento.** A página do perfil leva ~10s para hidratar; ler
antes disso devolve "Algo deu errado" e parece bloqueio. Depois de um perfil carregado
com sucesso, o seguinte costuma falhar: no máximo 2 por rodada, com pausa de 1–2 min.
Data e hora de cada vídeo saem do próprio id: `Number(BigInt(id) >> 32n)`.

**Um `carry` do dia bloqueia a medição real do mesmo dia.** `aplicar_contadores` pula
qualquer perfil que já tenha linha de hoje, então uma rodada que escreve carry cego
impede uma rodada posterior de gravar o valor medido. Enquanto o `saturno.py` não for
corrigido para deixar `medido` sobrescrever `carry`, junte Instagram e TikTok e aplique
os contadores uma única vez por rodada.

**`git push` do container é bloqueado** pelo proxy (403 — o repositório não está nas
fontes autorizadas da sessão, e não há tela no Cowork para autorizar). O transporte é
por upload no Chrome logado, em `/upload/main`. O botão verde "Commit changes"
frequentemente só rola a página: tire um screenshot, veja a posição nova e clique de
novo. Publicação só conta depois de conferida por `git fetch` + `git diff origin/main HEAD`.

## Adiado, não descartado

Migrar Instagram e TikTok para as APIs oficiais. No Instagram existe caminho sem App
Review para contas próprias (Instagram API with Instagram Login, escopos
`instagram_business_basic` + `instagram_business_manage_insights`), que tiraria a
dependência do computador ligado. Custos: contas precisam ser profissionais, cada uma
autorizada por quem a administra, token de 60 dias com renovação automatizada, e
insights podendo atrasar até 48h — o que precisa ser medido antes de confiar.

## TikTok — o que funciona e o que não funciona (02/09/2026)

A **grade de vídeos não hidrata mais**. `[data-e2e="user-post-item"]` fica em 0
em todos os 9 perfis, mesmo com o header já carregado e mesmo esperando 30s.
`api/post/item_list/` responde **200 com corpo vazio** — é o bloqueio do TikTok
a requisição sem assinatura, não um erro de rede. Não gaste rodadas nisso.

O que **funciona**: o blob `__UNIVERSAL_DATA_FOR_REHYDRATION__` da página do
perfil, em `__DEFAULT_SCOPE__["webapp.user-detail"].userInfo.stats` —
`followerCount`, `videoCount`, `heartCount`, exatos. Navegue para
`tiktok.com/@<handle>`, espere ~9s, leia o blob; um ERR na primeira tentativa
costuma passar na segunda.

Não use os números do DOM (`[data-e2e="followers-count"]` devolve "264.6K",
arredondado) — um contador arredondado gravado como `medido` é pior do que um
carry honesto.

Handles: acasasaturno, oikysha, aminequerida_, evybaddiee, orussindomolejo,
oiargentino_, oiikaka__, oifidelisx, kyshaeminee.

Resultado: desde 02/09 os contadores de TikTok voltaram a ser `medido` nos 9
perfis — eram carry havia semanas. Só a série de **posts** do TikTok segue
parada.

## Horários das rodadas

- 11h00 (14:00 UTC) — rodada da manhã.
- 18h10 (21:10 UTC) — rodada da noite. Era 19h10 até 02/09; mudou porque o
  computador estava desligado nas três tentativas (30/08, 31/08, 01/09).
- Actions: cron 12:00 UTC, só YouTube pela Data API.
