#!/bin/zsh
# Rodada local do Monitor Casa Saturno — Instagram (navegador próprio) + TikTok (embed),
# painel e publicação por git push. Roda pelo launchd (ver OPERACAO.md) ou na mão:
#   zsh pipeline/rodada_local.sh
#
# Desenho (desde 20/10/2026): COLETAR e PUBLICAR são etapas separadas.
#  1. o repositório é colocado em main, igual a origin/main, custe o que custar
#     (rebase pela metade, commit preso, base suja — tudo descartado; a verdade é o remoto);
#  2. cada coletor grava um SNAPSHOT em pipeline/_coleta/ e não toca na base;
#  3. publicar = reaplicar TODOS os snapshots pendentes sobre a base limpa, regenerar o
#     painel, commitar e dar push. Se o push for recusado (o Actions publicou no meio),
#     volta para origin/main e reaplica. Snapshot só é apagado depois de publicado:
#     rodada sem internet publica na seguinte, sem perder nada.
#  Por que: em 25/09/2026 o desenho antigo (aplicar direto + pull --rebase) parou num
#  conflito e 38 rodadas ficaram presas sem publicar, com a base cheia de marcadores.
set -u
REPO="${MONITOR_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${MONITOR_PYTHON:-$REPO/.venv/bin/python}"
LOGDIR="$HOME/Library/Logs/MonitorSaturno"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/rodada-$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1
echo "=== rodada $(date '+%F %H:%M:%S') repo=$REPO ==="
cd "$REPO" || exit 1
[ -x "$PY" ] || { echo "python do venv nao encontrado em $PY (veja OPERACAO.md)"; exit 1; }
SNAP="$REPO/pipeline/_coleta"; mkdir -p "$SNAP"
TS="$(date +%Y%m%d-%H%M%S)"

limpar_tmp() { rm -f pipeline/base_atual.xlsx pipeline/_regen_run.py pipeline/painel_casa_saturno.html pipeline/index.html; }

# ---------------------------------------------------------------- 1. repositório são
preparar_repo() {
  git rebase --abort >/dev/null 2>&1; git merge --abort >/dev/null 2>&1
  git checkout -q -f main || return 1
  if git fetch -q origin main; then
    git reset -q --hard origin/main
    git clean -q -fd pipeline/base
    echo "repo: main = origin/main ($(git log -1 --format=%h))"
  else
    git reset -q --hard
    echo "aviso: sem acesso ao remoto; coleta segue, publicacao fica para a proxima rodada"
    return 2
  fi
}
preparar_repo; ONLINE=$?
limpar_tmp

# ---------------------------------------------------------------- 2. coletas → snapshots
"$PY" pipeline/coletar_instagram.py --snapshot "$SNAP/ig-$TS.json" --nao-aplicar; RC_IG=$?
"$PY" pipeline/coletar_tiktok.py    --snapshot "$SNAP/tk-$TS.json" --nao-aplicar; RC_TK=$?
echo "instagram rc=$RC_IG tiktok rc=$RC_TK"
PEND=( "$SNAP"/*.json(N) )
if [ ${#PEND[@]} -eq 0 ]; then echo "nenhum snapshot pendente — nada a publicar"; exit 0; fi
echo "snapshots pendentes: ${#PEND[@]}"
[ "$ONLINE" -ne 0 ] && { echo "offline: snapshots guardados para a proxima rodada"; exit 0; }

# ---------------------------------------------------------------- 3. publicar (com uma repetição)
publicar() {
  limpar_tmp
  "$PY" pipeline/aplicar_snapshots.py --csv pipeline/base "${PEND[@]}" || return 1
  COLETA="$(TZ=America/Sao_Paulo date '+%Y-%m-%d %H:%M')"; HOJE="${COLETA:0:10}"
  sed -e "s/^COLETA=\"[^\"]*\"; HOJE=\"[^\"]*\"/COLETA=\"$COLETA\"; HOJE=\"$HOJE\"/" pipeline/regen.py > pipeline/_regen_run.py
  ( cd pipeline && "$PY" _regen_run.py ) || return 1
  mv -f pipeline/index.html index.html
  limpar_tmp
  git add index.html pipeline/base
  if git diff --cached --quiet -- pipeline/base; then
    echo "base inalterada apos aplicar snapshots — sem commit"; git reset -q --hard; return 0
  fi
  MSG="Rodada local $COLETA — ${#PEND[@]} snapshot(s)"
  [ $RC_IG -eq 0 ] && MSG="$MSG, Instagram" || MSG="$MSG, Instagram com falhas (rc=$RC_IG)"
  [ $RC_TK -eq 0 ] && MSG="$MSG, TikTok"    || MSG="$MSG, TikTok com falhas (rc=$RC_TK)"
  git commit -q -m "$MSG" || return 1
  git push -q origin main && { echo "publicado: $MSG"; return 0; }
  return 9
}
publicar; RC=$?
if [ $RC -eq 9 ]; then
  echo "push recusado (o remoto andou) — reaplicando sobre origin/main"
  git fetch -q origin main && git reset -q --hard origin/main && publicar; RC=$?
fi
if [ $RC -eq 0 ]; then
  rm -f "${PEND[@]}"; echo "snapshots publicados e removidos"
else
  echo "FALHA ao publicar (rc=$RC); snapshots mantidos para a proxima rodada"
  git reset -q --hard origin/main 2>/dev/null
fi
limpar_tmp
exit $RC
