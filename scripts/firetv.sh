#!/usr/bin/env bash
# Install / launch Crayon Cinema on a Fire TV over the network.
#   scripts/firetv.sh connect 192.168.1.50         # once per session (accept the prompt on the TV)
#   scripts/firetv.sh install                      # build + install debug APK
#   scripts/firetv.sh dev                          # point the TV app at this Mac's dev server and launch
#   scripts/firetv.sh record demo.mp4              # record up to 3 min of the TV screen (if supported)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-$ROOT/.tools/jdk/Contents/Home}"
export ANDROID_HOME="${ANDROID_HOME:-$ROOT/.tools/android-sdk}"
ADB="${ADB:-$ANDROID_HOME/platform-tools/adb}"
PKG=com.crayoncinema.tv

lan_ip() { ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1; }

case "${1:-}" in
  connect) "$ADB" connect "${2:?fire tv ip}:5555" && "$ADB" devices ;;
  install) (cd "$ROOT/firetv-app" && ./gradlew assembleDebug --no-daemon -q) && "$ADB" install -r "$ROOT/firetv-app/app/build/outputs/apk/debug/app-debug.apk" ;;
  dev)
    url="http://$(lan_ip):${CRAYON_PORT:-8787}/tv/"
    echo "Launching $PKG -> $url"
    "$ADB" shell am start -n "$PKG/.MainActivity" --es url "$url" ;;
  launch) "$ADB" shell am start -n "$PKG/.MainActivity" ;;
  record)
    out="${2:-firetv-demo.mp4}"
    echo "Recording (Ctrl+C to stop, max 180s)…"
    "$ADB" shell screenrecord --time-limit 180 /sdcard/crayon.mp4 || true
    "$ADB" pull /sdcard/crayon.mp4 "$out" && "$ADB" shell rm /sdcard/crayon.mp4 && echo "saved $out" ;;
  logs) "$ADB" logcat -s CrayonCinema chromium ;;
  *) sed -n '2,6p' "$0"; exit 1 ;;
esac
