#!/bin/zsh -f
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PYGAME_HIDE_SUPPORT_PROMPT=1
export GLOG_minloglevel=2

RES_DIR="${0:A:h}"
APP_BUNDLE_PARENT="${RES_DIR:h:h:h}"
APP_SUPPORT="$HOME/Library/Application Support/VanishCam"
mkdir -p "$APP_SUPPORT/logs" "$APP_SUPPORT/models"

cd "$RES_DIR" || exit 1
# Fix any insecure zsh completion directories permanently
/bin/zsh -fc 'autoload -Uz compaudit && compaudit 2>/dev/null | xargs chmod g-w,o-w 2>/dev/null' || true

echo "==================================================="
echo "  VanishCam for macOS (Goku / Particles / Naruto)"
echo "==================================================="

# 1. Copy any already-downloaded models from common folders so we don't re-download
for mdir in \
    "$APP_BUNDLE_PARENT/models" \
    "$HOME/vanish_webcam-main/models" \
    "$HOME/vanish_webcam_goku/models" \
    "$HOME/Downloads/vanish_webcam-main/models" \
    "$HOME/Downloads/vanish_webcam_goku/models" \
    "$HOME/Desktop/vanish_webcam-main/models" \
    "$HOME/Desktop/vanish_webcam_goku/models"; do
    if [[ -d "$mdir" ]]; then
        /bin/cp -n "$mdir"/* "$APP_SUPPORT/models/" 2>/dev/null || true
        /bin/cp -n "$mdir"/* "$RES_DIR/models/" 2>/dev/null || true
    fi
done

# 2. Locate an existing .venv on the Mac (searching common directories even if AppTranslocated)
VENV_PYTHON=""
candidates=(
    "$RES_DIR/.venv/bin/python"
    "$APP_BUNDLE_PARENT/.venv/bin/python"
    "$APP_SUPPORT/.venv/bin/python"
    "$HOME/vanish_webcam-main/.venv/bin/python"
    "$HOME/vanish_webcam_goku/.venv/bin/python"
    "$HOME/Downloads/vanish_webcam-main/.venv/bin/python"
    "$HOME/Downloads/vanish_webcam_goku/.venv/bin/python"
    "$HOME/Desktop/vanish_webcam-main/.venv/bin/python"
    "$HOME/Desktop/vanish_webcam_goku/.venv/bin/python"
)

for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
        VENV_PYTHON="$candidate"
        break
    fi
done

# Also check any vanish_webcam* folder in Home, Downloads, or Desktop
if [[ -z "$VENV_PYTHON" ]]; then
    found=$(/usr/bin/find "$HOME/Downloads" "$HOME/Desktop" "$HOME" -maxdepth 3 -path "*vanish*/*.venv/bin/python" 2>/dev/null | /usr/bin/head -n 1)
    if [[ -n "$found" && -x "$found" ]]; then
        VENV_PYTHON="$found"
    fi
fi

if [[ -z "$VENV_PYTHON" ]]; then
    SYS_PY=""
    for py in \
        /opt/homebrew/bin/python3.11 \
        /opt/homebrew/bin/python3.10 \
        /opt/homebrew/bin/python3.12 \
        "$HOME/miniconda3/bin/python3" \
        "$HOME/anaconda3/bin/python3" \
        /opt/miniconda3/bin/python3 \
        /opt/anaconda3/bin/python3 \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        /usr/bin/python3; do
        if [[ -x "$py" ]]; then
            SYS_PY="$py"
            break
        fi
    done

    echo "First launch: setting up Python virtual environment in $APP_SUPPORT/.venv ..."
    "$SYS_PY" -m venv "$APP_SUPPORT/.venv"
    "$APP_SUPPORT/.venv/bin/pip" install --upgrade pip
    "$APP_SUPPORT/.venv/bin/pip" install -r "$RES_DIR/requirements.txt"
    VENV_PYTHON="$APP_SUPPORT/.venv/bin/python"
fi

echo "Using Python: $VENV_PYTHON"
"$VENV_PYTHON" "$RES_DIR/vanish_cam.py" --no-virtual-camera "$@"
EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "[VanishCam exited with code $EXIT_CODE]"
    read -k 1 "?Press any key to close..."
fi
exit $EXIT_CODE
