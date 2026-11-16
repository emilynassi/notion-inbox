#!/bin/bash
# Set up the Bear Board on this Mac.
#
#   bear_board/install.sh              # check, set password, start at login, share over Tailscale if present
#   bear_board/install.sh --no-autostart
#   bear_board/install.sh --dry-run    # show what would happen, change nothing
#   bear_board/install.sh --uninstall  # stop it and remove the login item
#
# The board runs on 127.0.0.1 only. Other computers reach it through
# Tailscale (https://tailscale.com), which only devices signed in to your
# own Tailscale account can use, and the board's own password login.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="local.bear-board"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/bear-board.log"
PORT="${BEAR_BOARD_PORT:-8787}"
BEARCLI="${BEARCLI:-/Applications/Bear.app/Contents/MacOS/bearcli}"
AUTOSTART=1 DRY=0

for arg in "$@"; do
  case "$arg" in
    --no-autostart) AUTOSTART=0 ;;
    --dry-run) DRY=1 ;;
    --uninstall)
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
      rm -f "$PLIST"
      echo "Removed the login item. Your password config is still in ~/.config/bear-board/."
      echo "If you shared it over Tailscale, stop that with:  tailscale serve --https=443 off"
      exit 0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

run() { if [ "$DRY" = 1 ]; then echo "  [dry run] $*"; else "$@"; fi; }
ok() { echo "✓ $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

# 1. Requirements
[ "$(uname)" = "Darwin" ] || fail "The board has to run on a Mac with Bear. Reach it from other computers over Tailscale."
[ -x "$BEARCLI" ] || fail "Bear 2 isn't installed (no bearcli at $BEARCLI). Install Bear from the Mac App Store and sign in so your notes sync."
PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  fail "Python 3.9+ is needed. Run:  xcode-select --install"
fi
ok "Bear and Python ($("$PY" --version 2>&1)) found"

# 2. Password
if "$PY" -c "import sys; sys.path.insert(0, '$DIR'); import auth; sys.exit(0 if auth.load_config() else 1)"; then
  ok "Password already set (change it with: $PY $DIR/server.py --set-password)"
else
  echo "Choose a password for the board:"
  run "$PY" "$DIR/server.py" --set-password
fi

# 3. Tailscale (optional)
TS=""
for c in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then TS="$c"; break; fi
done
TS_HOST=""
if [ -n "$TS" ]; then
  TS_HOST="$("$TS" status --json 2>/dev/null | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
fi
if [ -n "$TS_HOST" ]; then
  ok "Tailscale is on: this Mac is $TS_HOST"
else
  echo "• Tailscale not found or not signed in. The board will only be reachable on this Mac."
  echo "  To use it from other computers: install Tailscale here and on them, sign in to the same account, then re-run this script."
fi

# 4. Start at login
if [ "$AUTOSTART" = 1 ]; then
  PLIST_XML="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/server.py</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>BEAR_BOARD_PORT</key><string>$PORT</string>
    <key>BEAR_BOARD_HOSTS</key><string>$TS_HOST</string>
    <key>BEARCLI</key><string>$BEARCLI</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>"
  if [ "$DRY" = 1 ]; then
    echo "  [dry run] would write $PLIST:"; echo "$PLIST_XML" | sed 's/^/    /'
  else
    mkdir -p "$(dirname "$PLIST")"
    printf '%s\n' "$PLIST_XML" > "$PLIST"
  fi
  run launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  run launchctl bootstrap "gui/$(id -u)" "$PLIST"
  ok "Board starts at login (logs: $LOG)"
else
  echo "• Not starting at login. Run it yourself with:  BEAR_BOARD_HOSTS=$TS_HOST $PY $DIR/server.py"
fi

# 5. Share over Tailscale (HTTPS, only your own devices)
if [ -n "$TS_HOST" ]; then
  run "$TS" serve --bg --https=443 "http://127.0.0.1:$PORT"
  ok "Shared over Tailscale"
fi

echo
echo "Open the board:"
echo "  On this Mac:          http://127.0.0.1:$PORT"
[ -n "$TS_HOST" ] && echo "  On your other devices: https://$TS_HOST"
exit 0
