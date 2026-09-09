#!/bin/zsh
# Instala a rodada local do Monitor Casa Saturno neste Mac:
#   1. venv em <repo>/.venv com playwright + openpyxl + requests, e o Chromium do Playwright;
#   2. agente do launchd que roda pipeline/rodada_local.sh às 11h00 e 18h10 (horário do Mac),
#      e também na carga do agente (login/boot) se o horário já passou — o launchd
#      executa rodadas perdidas quando a máquina acorda do sleep, mas não se estava desligada.
# Depois de instalar, faça o login UMA vez:  .venv/bin/python pipeline/coletar_instagram.py --login
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet playwright openpyxl requests
.venv/bin/python -m playwright install chromium
chmod +x pipeline/rodada_local.sh

LABEL="com.casasaturno.monitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/MonitorSaturno"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$REPO/pipeline/rodada_local.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>10</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/MonitorSaturno/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/MonitorSaturno/launchd.err.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "instalado: $PLIST"
echo "agora rode:  .venv/bin/python pipeline/coletar_instagram.py --login"
echo "teste manual: zsh pipeline/rodada_local.sh ; log em ~/Library/Logs/MonitorSaturno/"
