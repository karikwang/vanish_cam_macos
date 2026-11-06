# VanishCam for macOS (Goku Instant Transmission / Naruto / Particles / Dissolve)

<p align="left">
  <strong>🌐 Language / 语言:</strong>
  <a href="./README.md">简体中文</a> | <b>English</b>
</p>


> Real-time webcam disappearance & Dragon Ball Goku Instant Transmission (Shunkan Ido) effects for macOS and Windows — powered by MediaPipe & OpenCV, featuring system-wide global hotkeys (`Command + Shift + T`), native macOS desktop HUD alerts, and 100% clean video output.

This repository is an enhanced macOS port & expansion based on [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam). It implements the Goku Instant Transmission mode (two fingers on the forehead) and Particles mode, fixes the MediaPipe Metal crash on Apple Silicon Macs (M1/M2/M3/M4), and adds live camera switching, global hotkeys, and a pre-packaged `VanishCam.app` / `VanishCam_macOS.dmg`.

## 📥 How to Download (For Non-Coders & Beginners)

You don't need to know how to code or use Git to run this app:

### Option A: Download the `.dmg` Installer directly (Recommended)

1. Click on **[`release/VanishCam_macOS.dmg`](./release/VanishCam_macOS.dmg)** in this repository (or download `VanishCam_macOS.dmg` from the Releases section on the right).
2. Double-click `VanishCam_macOS.dmg` to mount it, drag `VanishCam.app` to your Desktop or `Applications` folder, and double-click to run!

### Option B: Download the Repository ZIP

1. Click the green `< > Code` button near the top-right of this GitHub page, then click `Download ZIP` at the bottom of the dropdown menu.
2. Open your `Downloads` folder on macOS, double-click the downloaded `.zip` file to extract it, and double-click `VanishCam.app`!
3. *(Note: On the very first launch, the app automatically configures its Python environment in the background, which takes ~1 minute. If macOS shows an "unidentified developer" prompt, simply Right-Click (or Control-Click) `VanishCam.app` -> Select "Open").*

*(Developers using Git can also clone the repository directly via `git clone <repo-url>`)*

## ✨ Key Features

1. **Four Real-Time Vanish Modes**:
   * 1 - Normal Vanish: Show a V sign to smoothly dissolve into the background with a cyan sparkle edge (3.6s).
   * 2 - Naruto Vanish (Body Substitution): Bring both palms together to vanish in a cloud of procedural smoke while a wooden substitution log drops to the floor (`assets/vanish.MP3`).
   * 3 - Particles: Show a V sign (peace sign) to shatter your silhouette into colored fragments that drift away in the wind (2.1s).
   * 4 - Goku Teleport (Instant Transmission): Hold your index and middle fingers straight and together against your forehead for 1 second. Animated vertical manga speed lines streak across your silhouette with the classic teleport sound (`assets/teleport.MP3`) as you vanish. Lower your hand and repeat the gesture for 1 second to teleport back!
2. **Global Hotkey for Gesture Recognition (`Command + Shift + T`)**:
   * Gesture detection stays OFF by default after background capture so your webcam runs at 100% native smooth FPS with zero extra CPU load during meetings.
   * Press `Command + Shift + T` at any time (even while Zoom, Tencent Meeting, Teams, or your browser is in fullscreen) to toggle gesture recognition ON or OFF.
3. **Manual Camera Selector & Live Camera Hot-Swap (`Command + Shift + C` / `C`)**:
   * Choose your webcam device directly in the startup menu before launching, or press `C` / `Command + Shift + C` at any time while running to hot-swap to the next available camera and recalibrate the background.
4. **100% Clean Video for OBS (Independent Desktop HUD + macOS Notifications)**:
   * Status prompts appear in an independent top-of-screen macOS floating HUD panel (`NSPanel`) and macOS Notification Center for 3 seconds — never drawn onto the webcam video frame, so meeting participants watching your OBS Virtual Camera never see any text overlays.
5. **Ready-to-Run macOS App & DMG (`VanishCam.app` & `release/VanishCam_macOS.dmg`)**:
   * Includes both the native `VanishCam.app` bundle and pre-packaged `release/VanishCam_macOS.dmg` disk image.

## 🚀 Quick Start (macOS)

### Option 1: Double-Click the macOS App (No Terminal Required)

1. Double-click `VanishCam.app` (or open `release/VanishCam_macOS.dmg`).
2. If macOS Gatekeeper prompts on first launch, Right-Click `VanishCam.app` -> Click "Open".

### Option 2: Run from Terminal

```zsh
# 1. Create and activate a Python virtual environment (Python 3.10 or 3.11 recommended)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies (automatically pins a stable MediaPipe build on macOS Apple Silicon)
pip install -r requirements.txt

# 3. Start Goku Instant Transmission mode directly
python3 vanish_cam.py --mode goku --no-virtual-camera

# Or open the interactive 1-4 mode & camera selection menu
./vanish --no-virtual-camera
```

## 🎮 Workflow & Controls

```text
Launch App ──► 10s countdown to capture clean background (step out of frame)
           ──► Full-FPS standby (gesture detection OFF, zero frame drop)
           ──► Press Command + Shift + T (turns gesture detection ON with 3s desktop banner)
           ──► Hold 2 fingers on forehead for 1s ──► Instant Transmission vanish!
           ──► Hold 2 fingers on forehead for 1s again ──► Teleport back in!
           ──► Press Command + Shift + T again (turns gesture detection OFF, full FPS)
```

| Shortcut                                                  | Action                                                       |
| :-------------------------------------------------------- | :----------------------------------------------------------- |
| `Command + Shift + T` *(Global)* or `T` *(In Window)*     | Toggle gesture recognition ON / OFF (works in the background across all apps) |
| `Command + Shift + C` *(Global)* or `C` *(Menu / Window)* | Switch webcam device (selectable in the start menu or hot-swappable live) |
| `SPACE` / `W`                                             | Recapture background (starts a new 10-second countdown)      |
| `F`                                                       | Toggle fullscreen preview                                    |
| `V` / `R`                                                 | Manually trigger vanish / reappear (disabled in Goku mode — gesture only) |
| `Q` / `ESC`                                               | Quit and release camera resources                            |

## 🎥 Using in Online Meetings & Browsers (OBS Virtual Camera)

1. Open [OBS Studio](https://obsproject.com/), click `+` under Sources, and select macOS Screen Capture (or Window Capture).
2. Set Method to Window Capture and select `[python3] Webcam - Preview` (uncheck "Show Cursor").
3. Click Start Virtual Camera in the bottom-right corner of OBS.
4. Select `OBS Virtual Camera` as your camera in Zoom, Microsoft Teams, Google Meet, Tencent Meeting, or your web browser.

## 🙏 Acknowledgements & License

* Upstream Attribution: Original concept and base implementation by Nico Auriemma ([Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam)). Huge thanks to the original author for the creative idea!
* **Contributions in this Fork**:
  * Implemented from scratch the open-source Goku Instant Transmission mode (`goku_effect.py`) and Particles mode (`particles_effect.py`).
  * Added macOS system-wide global hotkeys (`Command + Shift + T` / `Command + Shift + C`), interactive camera selection & live hot-swapping, and native macOS floating HUD (`NSPanel`) + Notification Center alerts.
  * Resolved the Apple Silicon MediaPipe Metal crash and packaged `VanishCam.app` and `VanishCam_macOS.dmg` for macOS.
* **License & Disclaimer**:
  * All new code and macOS enhancements added in this repository are released under the [MIT License](./LICENSE) for personal, educational, and non-commercial use.
  * Original base files remain subject to [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam). Audio clips and anime-inspired visual concepts (*Dragon Ball*, *Naruto*) belong to their respective copyright holders.
