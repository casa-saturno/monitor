# Monitor Casa Saturno — operação

Quem faz o quê, o que já quebrou e como voltar atrás. Atualizado em 09/09/2026.

## Quem coleta o quê

| | quem | quando | estado |
|---|---|---|---|
| YouTube | GitHub Actions (`.github/workflows/monitor.yml`), Data API v3 | diário, 12:00 UTC (9h BRT) | automático, não depende de máquina ligada |
| TikTok | GitHub Actions, `pipeline/coletar_tiktok.py` (embed público, sem sessão) | na mesma rodada do YouTube | automático, não depende de máquina ligada |
| Instagram | `pipeline/rodada_local.sh` via launchd neste Mac, `pipeline/coletar_instagram.py` (Chromium próprio, perfil logado) | 11h00 e 18h10 (hora do Mac) | depende do Mac ligado; NÃO depende de Cowork, da extensão do Chrome nem de upload manual |
| Publicação | commit de `index.html` + `pipeline/base` (GitHub Pages) | a cada rodada | Actions: token do próprio workflow. Local: `git push` por SSH da conta casa-saturno |

A rodada local também roda o coletor de TikTok, para o painel das 11h e das 18h
ter TikTok fresco, não só o das 9h.

## Rodada local — instalação e manutenção (09/09/2026)

```
zsh pipeline/instalar_local.sh                       # venv + Chromium + agente do launchd
.venv/bin/python pipeline/coletar_instagram.py --login   # login humano, UMA vez; feche a janela ao terminar
zsh pipeline/rodada_local.sh                         # teste; log em ~/Library/Logs/MonitorSaturno/
```

- O perfil do navegador fica em `~/Library/Application Support/MonitorSaturno/chromium-profile`.
  É uma sessão separada da do Chrome de uso pessoal. Quando expirar, o log mostra
  `sessão expirada? rode --login` e a rodada segue só com TikTok.
- Diagnóstico com janela: `.venv/bin/python pipeline/coletar_instagram.py --dry-run --headed --perfis 1`.
- Desinstalar o agente: `launchctl bootout gui/$(id -u)/com.casasaturno.monitor`.
- O launchd executa rodadas perdidas quando o Mac acorda do sleep, mas não se
  ele estava desligado. Dia sem rodada local = dia sem Instagram, e só.

## O que a coleta de Instagram usa hoje (e o que morreu)

| rota | estado em 09/09/2026 |
|---|---|
| `/api/v1/feed/user/<uid>/?count=12` | **morta**: 200 redirecionado para a home, HTML. Desde 04/09. |
| `/api/v1/users/web_profile_info/` | morta desde agosto (400 / 401). |
| página de perfil → árvore React dos itens da grade | **funciona**: code, taken_at, tipo, legenda, coautores, likes, comentários. Sem views. |
| `/api/v1/users/<uid>/info/` | **funciona**: seguidores e total de posts, exatos. |
| `/api/v1/media/<pk>/info/` | **funciona**: `play_count` de Reels, exato, mesma métrica do feed antigo (conferido contra a base de 03/09: 102.522 → 103.833 no mesmo Reel). |

## Caminho definitivo, ainda não feito: API oficial no Actions

O que tira o Instagram da dependência de um Mac ligado é a **Instagram API with
Instagram Login** (sem Facebook Page, sem App Review para contas com papel no app):

1. Criar um app em developers.facebook.com, produto "Instagram", caso de uso
   "API with Instagram Login". Modo de desenvolvimento basta.
2. Cada uma das 9 contas precisa ser Profissional (Business ou Creator) e ser
   adicionada como *Instagram Tester* do app; quem administra a conta aceita o
   convite no app do Instagram.
3. Autorizar cada conta uma vez (`instagram_business_basic`,
   `instagram_business_manage_insights`) e trocar o code por token longo (60 dias).
4. No Actions: `GET graph.instagram.com/me?fields=followers_count,media_count`,
   `GET /me/media?fields=id,shortcode,caption,media_type,media_product_type,timestamp,like_count,comments_count&limit=12`
   e `GET /<media_id>/insights?metric=views` — tudo por token, sem navegador.
   Renovação: `GET /refresh_access_token?grant_type=ig_refresh_token` a cada rodada,
   guardando o token novo (secret por conta, atualizado via `gh secret set`).
5. Registrar a fonte `ig_api` no `saturno.py` (já existe em FONTES) e rodar em
   paralelo com a rodada local por uma semana para comparar números antes de
   desligar o navegador.

Para o TikTok o equivalente é a Display API (`user.info.stats`, `video.list`), que
exige aprovação do app pelo TikTok e OAuth de cada criador. Enquanto o embed
funcionar, não vale o custo.

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

## TikTok — embed público (09/09/2026)

A página de perfil é protegida por gestão de bots (Akamai): "Please wait…",
depois "acesso negado", em qualquer navegador automatizado — e em 09/09 até no
Chrome pessoal com a extensão. Já os endpoints de **embed**, feitos para sites
de terceiros, respondem a um GET sem cookie:

- `tiktok.com/embed/@<handle>` → seguidores, curtidas totais e os 12 vídeos
  mais recentes com views;
- `tiktok.com/embed/v2/<video_id>` → data, views, likes, comentários, compartilhamentos.

`coletar_tiktok.py` lê os dois. Validado nos 9 perfis: 93 vídeos, 0 falhas.
**Precisão**: acima de 10.000 os números vêm com 3 algarismos significativos
(11.800, 2.800.000); abaixo são exatos. É exatamente a precisão do blob
`__UNIVERSAL_DATA_FOR_REHYDRATION__` que vínhamos gravando como `medido`
(269.100 seguidores em ambos) — ou seja, os contadores de TikTok nunca foram
exatos, e a fonte `tk_embed` deixa isso rastreável. O embed de perfil não expõe
`videoCount`; o total de posts do dia anterior é mantido na linha medida.

Vale saber que o embed **precisa ser conferido de um IP de datacenter** na
primeira rodada do Actions: foi validado só a partir deste Mac.

## TikTok — histórico do que não funciona (02/09/2026)

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
