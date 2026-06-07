#!/usr/bin/env bash
# One-shot installer for text-to-simple-video.
#
# What this does:
#   1. Create .venv/ if missing
#   2. Install Python deps from requirements.txt
#   3. Download open-source CJK fonts into fonts/ (skips ones already present)
#   4. Print next-step hint
#
# Optional flags forwarded to fonts/download_fonts.py:
#   --mirror URL    GitHub proxy prefix (helpful from mainland China)
#   --force         redownload fonts even if files exist
#   --skip-fonts    only set up venv + deps, don't download fonts

set -euo pipefail
cd "$(dirname "$0")"

SKIP_FONTS=0
PASS_THROUGH=()
for arg in "$@"; do
    case "$arg" in
        --skip-fonts) SKIP_FONTS=1 ;;
        *) PASS_THROUGH+=("$arg") ;;
    esac
done

PYTHON=${PYTHON:-python3}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "❌  $PYTHON not found in PATH. Install Python 3.9+ first."
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "⚠️   ffmpeg / ffprobe not found in PATH."
    echo "    macOS:  brew install ffmpeg"
    echo "    Linux:  sudo apt install ffmpeg   (or your distro equivalent)"
fi

# 1. venv
if [[ ! -d .venv ]]; then
    echo "[1/3] Creating .venv with $($PYTHON --version 2>&1)…"
    "$PYTHON" -m venv .venv
else
    echo "[1/3] .venv already exists, reusing."
fi

# shellcheck source=/dev/null
source .venv/bin/activate

# 2. python deps + console script (`t2sv`)
echo "[2/3] Installing package (pyproject.toml) into .venv…"
pip install --quiet --upgrade pip
pip install --quiet -e .

# 3. fonts
if [[ "$SKIP_FONTS" -eq 1 ]]; then
    echo "[3/3] Skipping font download (--skip-fonts)."
else
    echo "[3/3] Downloading open-source CJK fonts (≈45 MB, skips existing)…"
    if ((${#PASS_THROUGH[@]})); then
        python fonts/download_fonts.py "${PASS_THROUGH[@]}"
    else
        python fonts/download_fonts.py
    fi
fi

cat <<EOF

✅  Setup complete.

Activate the venv and use the new \`t2sv\` shortcut from any directory:

    source .venv/bin/activate
    t2sv sample.txt                  # reads text/sample.txt, writes to video/<时间>_sample/
    t2sv --text "你好，世界" -o hello # one-liner, output in video/hello/

Or without activating:

    .venv/bin/t2sv sample.txt
EOF
