#!/bin/zsh -f
DIR="${0:A:h}"
/usr/bin/xattr -cr "$DIR/VanishCam.app" 2>/dev/null || true
if [[ -x "$DIR/VanishCam.app/Contents/Resources/run_vanishcam.sh" ]]; then
    exec /bin/zsh -f "$DIR/VanishCam.app/Contents/Resources/run_vanishcam.sh" --mode goku
elif [[ -x "/Applications/VanishCam.app/Contents/Resources/run_vanishcam.sh" ]]; then
    exec /bin/zsh -f "/Applications/VanishCam.app/Contents/Resources/run_vanishcam.sh" --mode goku
else
    cd "$DIR" || exit 1
    exec ./vanish goku --no-virtual-camera
fi
