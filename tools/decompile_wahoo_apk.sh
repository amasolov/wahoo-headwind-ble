#!/usr/bin/env bash
# Decompile the Wahoo app and pull out everything related to the Headwind
# BLE protocol, to cross-check custom_components/wahoo_headwind/protocol.py.
#
# Usage: tools/decompile_wahoo_apk.sh path/to/wahoo.apk [out_dir]
#
# Get the APK from a phone (`adb shell pm path com.wahoofitness.fitness`,
# then `adb pull`) or from an APK mirror. For split APKs / .xapk, unzip and
# pass the base.apk. Requires Java 11+; jadx is downloaded if missing.
set -euo pipefail

APK=${1:?usage: $0 app.apk [out_dir]}
OUT=${2:-wahoo_src}
JADX_VERSION=1.5.1

if ! command -v jadx >/dev/null; then
  if [ ! -x .jadx/bin/jadx ]; then
    echo "Downloading jadx $JADX_VERSION ..."
    curl -sSL -o /tmp/jadx.zip "https://github.com/skylot/jadx/releases/download/v$JADX_VERSION/jadx-$JADX_VERSION.zip"
    unzip -qo /tmp/jadx.zip -d .jadx
  fi
  JADX=.jadx/bin/jadx
else
  JADX=jadx
fi

[ -d "$OUT" ] || "$JADX" --no-res --show-bad-code -j "$(nproc)" -d "$OUT" "$APK" || true

echo
echo "=== Files mentioning the Headwind service/characteristic UUIDs ==="
grep -rliE "a026ee0c|a026e038|ee0c|e038" "$OUT/sources" | head -50 || true

echo
echo "=== Files mentioning Headwind ==="
grep -rli "headwind" "$OUT/sources" | head -50 || true

echo
echo "=== Likely opcode / mode definitions ==="
grep -rnE -i "headwind.*(mode|speed|opcode|packet)|(HR|HEART_RATE|SPEED|SLEEP|MANUAL)_?MODE" "$OUT/sources" \
  | grep -i -E "headwind|fan" | head -80 || true

echo
echo "Look at the files above for the class that builds the write packets"
echo "(typically a 'HeadwindPacket'/'FanPacket' style class with an opcode enum)"
echo "and the one that parses notifications; compare with docs/PROTOCOL.md."
