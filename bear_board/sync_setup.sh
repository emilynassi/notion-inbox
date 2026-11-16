#!/bin/bash
# Connect this Mac to the hosted Bear Board website.
#
#   bear_board/sync_setup.sh             # set up (or change the password), then sync every 10 min
#   bear_board/sync_setup.sh --uninstall # stop syncing
#
# Run it on the Mac that has Bear. It creates a private Python environment
# for the encryption library, asks for your site URL and board password,
# walks you through one Vercel setting, and starts syncing.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="$HOME/.config/bear-board"
VENV="$CONF/venv"
LABEL="local.bear-board-sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/bear-board-sync.log"
BEARCLI="${BEARCLI:-/Applications/Bear.app/Contents/MacOS/bearcli}"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Stopped syncing. The website keeps the last upload until you set it up again."
  exit 0
fi

[ "$(uname)" = "Darwin" ] || { echo "Run this on the Mac that has Bear." >&2; exit 1; }
[ -x "$BEARCLI" ] || { echo "Bear 2 isn't installed (no bearcli at $BEARCLI)." >&2; exit 1; }
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "Python 3 is needed. Run: xcode-select --install" >&2; exit 1; }

mkdir -p "$CONF" && chmod 700 "$CONF"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Setting up the encryption library (one time)…"
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --disable-pip-version-check "cryptography>=42"

"$VENV/bin/python" "$DIR/sync_agent.py" setup

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$VENV/bin/python</string><string>$DIR/sync_agent.py</string><string>run</string>
  </array>
  <key>EnvironmentVariables</key><dict><key>BEARCLI</key><string>$BEARCLI</string></dict>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✓ Syncing every 10 minutes while this Mac is awake (log: $LOG)"
