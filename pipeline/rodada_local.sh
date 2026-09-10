#!/bin/zsh
# Rodada local do Monitor Casa Saturno — Instagram (navegador próprio) + TikTok (embed),
# regeneração do painel e publicação por git push. Pensada para rodar pelo launchd
# (ver OPERACAO.md), mas roda igual na mão:  zsh pipeline/rodada_local.sh
#
# Regras:
#  - nunca deixa lixo no repo: base_atual.xlsx e _regen_run.py são apagados no fim;
#  - só comita se a base mudou; pull --rebase antes de push, como o workflow;
#  - falha de coleta numa plataforma não impede a outra nem a publicação;
#  - tudo vai para o log em ~/Library/Logs/MonitorSaturno/.
set -u
REPO="${MONITOR_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${MONITOR_PYTHON:-$REPO/.venv/bin/python}"
LOGDIR="$HOME/Library/Logs/MonitorSaturno"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/rodada-$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1
echo "=== rodada $(date '+%F %H:%M:%S') repo=$REPO ==="
cd "$REPO" || exit 1
[ -x "$PY" ] || { echo "python do venv nao encontrado em $PY (veja OPERACAO.md)"; exit 1; }

# 1. base: sempre a partir do espelho versionado, depois do pull
git pull --rebase --quiet || echo "aviso: git pull falhou; seguindo com a copia local"
rm -f pipeline/base_atual.xlsx
"$PY" -c "import sys; sys.path.insert(0,'pipeline'); import saturno; saturno.carregar_base_dos_csv('pipeline/base','pipeline/base_atual.xlsx')"

# 2. coletas — cada uma aplica na mesma base_atual.xlsx e reexporta os CSV
COLETA="$(TZ=America/Sao_Paulo date '+%Y-%m-%d %H:%M')"; HOJE="${COLETA:0:10}"
"$PY" pipeline/coletar_instagram.py; RC_IG=$?
"$PY" pipeline/coletar_tiktok.py;   RC_TK=$?
echo "instagram rc=$RC_IG tiktok rc=$RC_TK"

# 3. painel
sed -e "s/^COLETA=\"[^\"]*\"; HOJE=\"[^\"]*\"/COLETA=\"$COLETA\"; HOJE=\"$HOJE\"/" pipeline/regen.py > pipeline/_regen_run.py
( cd pipeline && "$PY" _regen_run.py ) && mv -f pipeline/index.html index.html
rm -f pipeline/_regen_run.py pipeline/base_atual.xlsx pipeline/painel_casa_saturno.html

# 4. publicação — só com mudança real na base
git add index.html pipeline/base
if git diff --cached --quiet -- pipeline/base; then
  echo "base inalterada — sem commit"; git reset --quiet
  exit 0
fi
MSG="Rodada local $COLETA"
[ $RC_IG -eq 0 ] && MSG="$MSG — Instagram" || MSG="$MSG — Instagram com falhas (rc=$RC_IG)"
[ $RC_TK -eq 0 ] && MSG="$MSG, TikTok"    || MSG="$MSG, TikTok com falhas (rc=$RC_TK)"
git commit --quiet -m "$MSG" && git pull --rebase --quiet && git push --quiet && echo "publicado: $MSG"
