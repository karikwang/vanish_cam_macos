"""Local webcam: vanish effects triggered by hand gestures (Normal, Naruto, Particles, Goku)."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from contextlib import ExitStack
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

try:
    from .naruto_effect import (
        EFFECT_SECONDS, joined_hands_from_landmarks, landed_log_anchor,
        load_log, overlay_log, render_reappearance, render_substitution, substitution_anchor,
    )
    from .goku_effect import (
        GOKU_EFFECT_SECONDS, GOKU_HOLD_SECONDS,
        estimate_forehead_from_detections, goku_forehead_pose_from_landmarks, render_goku_teleport,
    )
    from .particles_effect import (
        PARTICLES_SECONDS, ParticleSystem, render_particles,
    )
    from .vanish_sound import SOUND_PATH, TELEPORT_SOUND_PATH, VanishSound
except ImportError:
    from naruto_effect import (
        EFFECT_SECONDS, joined_hands_from_landmarks, landed_log_anchor,
        load_log, overlay_log, render_reappearance, render_substitution, substitution_anchor,
    )
    from goku_effect import (
        GOKU_EFFECT_SECONDS, GOKU_HOLD_SECONDS,
        estimate_forehead_from_detections, goku_forehead_pose_from_landmarks, render_goku_teleport,
    )
    from particles_effect import (
        PARTICLES_SECONDS, ParticleSystem, render_particles,
    )
    from vanish_sound import SOUND_PATH, TELEPORT_SOUND_PATH, VanishSound


APP_DIR = Path(__file__).resolve().parent
WINDOW_NAME = "Webcam - Preview"


def _resolve_writable_dir(subpath: str) -> Path:
    local_candidate = APP_DIR / subpath
    try:
        local_candidate.mkdir(parents=True, exist_ok=True)
        test_file = local_candidate / ".write_test"
        test_file.touch()
        test_file.unlink()
        return local_candidate
    except OSError:
        user_dir = Path.home() / "Library" / "Application Support" / "VanishCam" / subpath
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir


MODEL_DIR = _resolve_writable_dir("models")
LOG_DIR = _resolve_writable_dir("logs")

SEGMENTER_MODEL = MODEL_DIR / "selfie_segmenter_landscape.tflite"
GESTURE_MODEL = MODEL_DIR / "gesture_recognizer.task"
FACE_MODEL = MODEL_DIR / "blaze_face_short_range.tflite"
HAND_MODEL = APP_DIR / "hand_landmarker.task"

MODEL_URLS = {
    SEGMENTER_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
        "selfie_segmenter_landscape/float16/latest/"
        "selfie_segmenter_landscape.tflite"
    ),
    GESTURE_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
        "gesture_recognizer/float16/1/gesture_recognizer.task"
    ),
    FACE_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    ),
}

CALIBRATION_SECONDS = 10.0
BACKGROUND_SAMPLE_SECONDS = 0.55
VANISH_SECONDS = 3.6
REAPPEAR_SECONDS = 1.4
# The dissolve curve is nearly flat near 1.0, so the reverse starts lower to
# avoid a visible pause before the person starts returning.
REAPPEAR_START_PROGRESS = 0.7
GESTURE_INTERVAL_SECONDS = 0.14
HUD_TOAST_SECONDS = 3.0


def log(message: str) -> None:
    """Print a timestamped status line and keep a copy in logs/vanish-<date>.log."""
    now = datetime.now()
    line = f"[{now:%H:%M:%S}] {message}"
    print(line)
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with (LOG_DIR / f"vanish-{now:%Y-%m-%d}.log").open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError:
        pass  # The terminal line is enough if the log folder is not writable.


@dataclass
class AppState:
    phase: str = "calibrating"
    calibration_started: float = 0.0
    vanish_started: float | None = None
    last_gesture_check: float = 0.0
    fullscreen: bool = False
    # The same gesture toggles vanish/reappear, so it must be released between uses.
    gesture_armed: bool = True
    # Gesture detection is off by default until toggled on by Command+Shift+T (or T key)
    gesture_detection_enabled: bool = False
    goku_hold_started: float | None = None
    goku_last_countdown: int | None = None
    toast_message: str | None = None
    toast_until: float = 0.0


class GlobalHotkeyMonitor:
    """System-wide global shortcut monitor for:
      - Command+Shift+T: toggle gesture recognition ON/OFF
      - Command+Shift+C: switch to next webcam device live

    Uses macOS Carbon RegisterEventHotKey via ctypes so it works even when a meeting app
    (Zoom, Tencent Meeting, Teams, Chrome) is in the foreground.
    """

    def __init__(self) -> None:
        self._triggered = False
        self._camera_switch_triggered = False
        self._last_trigger_time = 0.0
        self._last_cam_trigger_time = 0.0
        self._carbon = None
        self._hotkey_ref = ctypes.c_void_p()
        self._hotkey_cam_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._c_callback = None
        self._nsevent_global = None
        self._nsevent_local = None
        self._setup()

    def _fire(self) -> None:
        now = time.perf_counter()
        if now - self._last_trigger_time >= 0.28:
            self._last_trigger_time = now
            self._triggered = True

    def _fire_camera_switch(self) -> None:
        now = time.perf_counter()
        if now - self._last_cam_trigger_time >= 0.45:
            self._last_cam_trigger_time = now
            self._camera_switch_triggered = True

    def _setup(self) -> None:
        if sys.platform == "darwin":
            self._setup_macos_carbon()
            self._setup_macos_nsevent()

    def _setup_macos_carbon(self) -> None:
        try:
            carbon_path = (
                ctypes.util.find_library("Carbon")
                or "/System/Library/Frameworks/Carbon.framework/Carbon"
            )
            carbon = ctypes.cdll.LoadLibrary(carbon_path)

            class EventTypeSpec(ctypes.Structure):
                _fields_ = [
                    ("eventClass", ctypes.c_uint32),
                    ("eventKind", ctypes.c_uint32),
                ]

            class EventHotKeyID(ctypes.Structure):
                _fields_ = [
                    ("signature", ctypes.c_uint32),
                    ("id", ctypes.c_uint32),
                ]

            HANDLER_FUNC = ctypes.CFUNCTYPE(
                ctypes.c_int32,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )

            # kEventParamDirectObject = '----' (0x2D2D2D2D), typeEventHotKeyID = 'hkid' (0x686B6964)
            carbon.GetEventParameter.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.POINTER(EventHotKeyID),
            ]
            carbon.GetEventParameter.restype = ctypes.c_int32

            def _on_hotkey(next_handler, event, user_data):
                hk_id = EventHotKeyID()
                err_param = carbon.GetEventParameter(
                    event,
                    0x2D2D2D2D,
                    0x686B6964,
                    None,
                    ctypes.sizeof(EventHotKeyID),
                    None,
                    ctypes.byref(hk_id),
                )
                if err_param == 0 and hk_id.id == 2:
                    self._fire_camera_switch()
                else:
                    self._fire()
                return 0  # noErr

            self._c_callback = HANDLER_FUNC(_on_hotkey)

            carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            target = carbon.GetApplicationEventTarget()

            # kEventClassKeyboard = 'keyb' (0x6B657962), kEventHotKeyPressed = 5
            spec = EventTypeSpec(0x6B657962, 5)
            carbon.InstallEventHandler.argtypes = [
                ctypes.c_void_p,
                HANDLER_FUNC,
                ctypes.c_uint32,
                ctypes.POINTER(EventTypeSpec),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            carbon.InstallEventHandler.restype = ctypes.c_int32
            err = carbon.InstallEventHandler(
                target,
                self._c_callback,
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(self._handler_ref),
            )

            # Virtual keycodes on macOS: 'T' = 17 (0x11), 'C' = 8 (0x08)
            # Carbon modifiers: cmdKey = 1 << 8 (256), shiftKey = 1 << 9 (512)
            carbon.RegisterEventHotKey.argtypes = [
                ctypes.c_uint32,
                ctypes.c_uint32,
                EventHotKeyID,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            carbon.RegisterEventHotKey.restype = ctypes.c_int32

            hotkey_t = EventHotKeyID(0x564E5348, 1)  # 'VNSH', 1 -> Command+Shift+T
            err_t = carbon.RegisterEventHotKey(
                17, 256 | 512, hotkey_t, target, 0, ctypes.byref(self._hotkey_ref)
            )
            hotkey_c = EventHotKeyID(0x564E5348, 2)  # 'VNSH', 2 -> Command+Shift+C
            err_c = carbon.RegisterEventHotKey(
                8, 256 | 512, hotkey_c, target, 0, ctypes.byref(self._hotkey_cam_ref)
            )
            if err == 0 and (err_t == 0 or err_c == 0):
                self._carbon = carbon
                log("Global hotkeys registered: Command+Shift+T (gesture ON/OFF), Command+Shift+C (switch camera).")
        except Exception as exc:
            log(f"Note: Carbon global hotkey fallback ({exc}).")

    def _setup_macos_nsevent(self) -> None:
        try:
            from AppKit import (
                NSEvent,
                NSKeyDownMask,
                NSCommandKeyMask,
                NSShiftKeyMask,
            )

            def _handle_event(event):
                try:
                    flags = int(event.modifierFlags())
                    cmd = bool(flags & int(NSCommandKeyMask))
                    shift = bool(flags & int(NSShiftKeyMask))
                    if cmd and shift:
                        kc = int(event.keyCode())
                        if kc == 17:
                            self._fire()
                        elif kc == 8:
                            self._fire_camera_switch()
                except Exception:
                    pass

            self._nsevent_global = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask, _handle_event
            )
            def _handle_local(event):
                _handle_event(event)
                return event

            self._nsevent_local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask, _handle_local
            )
        except Exception:
            pass

    def poll(self) -> bool:
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                if (
                    (user32.GetAsyncKeyState(0x11) & 0x8000)
                    and (user32.GetAsyncKeyState(0x10) & 0x8000)
                    and (user32.GetAsyncKeyState(0x54) & 0x8000)
                ):
                    self._fire()
            except Exception:
                pass
        if self._triggered:
            self._triggered = False
            return True
        return False

    def poll_camera_switch(self) -> bool:
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                # Control (0x11) + Shift (0x10) + C (0x43)
                if (
                    (user32.GetAsyncKeyState(0x11) & 0x8000)
                    and (user32.GetAsyncKeyState(0x10) & 0x8000)
                    and (user32.GetAsyncKeyState(0x43) & 0x8000)
                ):
                    self._fire_camera_switch()
            except Exception:
                pass
        if self._camera_switch_triggered:
            self._camera_switch_triggered = False
            return True
        return False

    def close(self) -> None:
        if self._carbon is not None:
            for ref in (self._hotkey_ref, self._hotkey_cam_ref):
                if ref:
                    try:
                        self._carbon.UnregisterEventHotKey(ref)
                    except Exception:
                        pass
            self._carbon = None


class DesktopToastOverlay:
    """Independent macOS desktop floating HUD banner + Notification Center banner.

    Because this is a separate NSWindow (and system notification) rather than drawn onto
    `Webcam - Preview`, OBS Window Capture on `[python3] Webcam - Preview` will NEVER capture
    it — only you can see it on your Mac screen.
    """

    def __init__(self) -> None:
        self._window = None
        self._label = None
        self._initialized = False

    def _ensure_window(self) -> bool:
        if self._initialized:
            return self._window is not None
        self._initialized = True
        if sys.platform != "darwin":
            return False
        try:
            from AppKit import (
                NSBackingStoreBuffered,
                NSColor,
                NSFont,
                NSMakeRect,
                 NSPanel,
                NSScreen,
                NSTextAlignmentCenter,
                NSTextField,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorIgnoresCycle,
                NSWindowStyleMaskBorderless,
                NSWindowStyleMaskNonactivatingPanel,
            )

            screen = NSScreen.mainScreen()
            if screen is None:
                return False
            sf = screen.frame()
            width, height = 660.0, 54.0
            x = sf.origin.x + (sf.size.width - width) / 2.0
            y = sf.origin.y + sf.size.height - height - 64.0

            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, width, height),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                NSBackingStoreBuffered,
                False,
            )
            # Floating status level above normal and fullscreen apps
            panel.setLevel_(25)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.09, 0.11, 0.14, 0.88)
            )
            panel.setHasShadow_(True)
            panel.setIgnoresMouseEvents_(True)
            panel.setHidesOnDeactivate_(False)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | NSWindowCollectionBehaviorIgnoresCycle
            )

            content = panel.contentView()
            content.setWantsLayer_(True)
            if content.layer() is not None:
                content.layer().setCornerRadius_(12.0)
                content.layer().setMasksToBounds_(True)

            label = NSTextField.alloc().initWithFrame_(NSMakeRect(16.0, 13.0, width - 32.0, 28.0))
            label.setEditable_(False)
            label.setSelectable_(False)
            label.setBezeled_(False)
            label.setDrawsBackground_(False)
            label.setAlignment_(NSTextAlignmentCenter)
            label.setTextColor_(NSColor.whiteColor())
            label.setFont_(NSFont.boldSystemFontOfSize_(15.5))
            content.addSubview_(label)

            self._window = panel
            self._label = label
            return True
        except Exception:
            self._window = None
            self._label = None
            return False

    def show_banner(self, message: str) -> None:
        if not self._ensure_window():
            return
        try:
            from AppKit import NSMakeRect, NSScreen

            screen = NSScreen.mainScreen()
            if screen is not None:
                sf = screen.frame()
                width, height = 660.0, 54.0
                x = sf.origin.x + (sf.size.width - width) / 2.0
                y = sf.origin.y + sf.size.height - height - 64.0
                self._window.setFrame_display_(NSMakeRect(x, y, width, height), False)
            self._label.setStringValue_(message)
            self._window.orderFrontRegardless()
        except Exception:
            pass

    def hide_banner(self) -> None:
        if self._window is not None:
            try:
                self._window.orderOut_(None)
            except Exception:
                pass

    def close(self) -> None:
        self.hide_banner()
        self._window = None
        self._label = None


_DESKTOP_TOAST = DesktopToastOverlay()


def send_macos_notification(message: str, title: str = "VanishCam") -> None:
    """Trigger a native macOS Notification Center banner in the background."""
    if sys.platform != "darwin":
        return
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{safe_msg}" with title "{safe_title}"'
    try:
        subprocess.Popen(
            ["/usr/bin/osascript", "-e", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def show_toast(
    state: AppState,
    message: str,
    now: float | None = None,
    duration: float = HUD_TOAST_SECONDS,
) -> None:
    """Show a 3-second desktop floating banner + macOS Notification Center alert (invisible to OBS)."""
    if now is None:
        now = time.perf_counter()
    state.toast_message = message
    state.toast_until = now + duration
    _DESKTOP_TOAST.show_banner(message)
    send_macos_notification(message)


def update_desktop_toast(state: AppState, now: float) -> None:
    """Auto-hide the desktop floating banner once its 3-second timer expires."""
    if state.toast_message is not None and now >= state.toast_until:
        state.toast_message = None
        _DESKTOP_TOAST.hide_banner()


def toggle_gesture_detection(state: AppState, now: float | None = None) -> None:
    """Toggle gesture recognition on/off and reset any partial hold countdown."""
    if now is None:
        now = time.perf_counter()
    state.gesture_detection_enabled = not state.gesture_detection_enabled
    state.goku_hold_started = None
    state.goku_last_countdown = None
    state.gesture_armed = True
    if state.gesture_detection_enabled:
        msg = "Gesture recognition: ON (Command+Shift+T). Waiting for gesture..."
        log(msg)
        show_toast(state, msg, now, HUD_TOAST_SECONDS)
    else:
        msg = "Gesture recognition: OFF (Command+Shift+T)."
        log("Gesture recognition: OFF (Command+Shift+T). Video running at full smooth FPS.")
        show_toast(state, msg, now, HUD_TOAST_SECONDS)


def positive_fps(value: str) -> float:
    fps = float(value)
    if not np.isfinite(fps) or not 1 <= fps <= 120:
        raise argparse.ArgumentTypeError("FPS must be between 1 and 120.")
    return fps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Choose Normal Vanish, Naruto Vanish, Particles, or Goku for the webcam."
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    parser.add_argument("--width", type=int, default=960, help="Video width")
    parser.add_argument("--height", type=int, default=540, help="Video height")
    parser.add_argument(
        "--fullscreen", action="store_true", help="Start in fullscreen"
    )
    parser.add_argument(
        "--no-mirror", action="store_true", help="Do not mirror the webcam"
    )
    parser.add_argument("--fps", type=positive_fps, default=30.0, help="Maximum virtual camera FPS (default: 30)")
    parser.add_argument(
        "--virtual-camera", action=argparse.BooleanOptionalAction, default=None,
        help="Require the virtual camera; by default it is used when available. --no-virtual-camera turns it off",
    )
    parser.add_argument(
        "--virtual-backend", choices=("obs", "unitycapture", "v4l2loopback"),
        help="Virtual camera driver to use",
    )
    parser.add_argument("--virtual-device", help="Virtual camera device name to use")
    parser.add_argument(
        "--mode", choices=("normal", "naruto", "particles", "goku"),
        help="Skip the menu and start this mode directly",
    )
    parser.add_argument(
        "--gesture-debug", action="store_true",
        help="Print gesture recognition status in the terminal (never drawn on the video)",
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def list_available_cameras(max_check: int = 5) -> list[tuple[int, str]]:
    """Discover available webcam indices and human-readable names (on macOS via system_profiler)."""
    names: list[str] = []
    if sys.platform == "darwin":
        try:
            import json
            res = subprocess.run(
                ["/usr/sbin/system_profiler", "SPCameraDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            data = json.loads(res.stdout or "{}")
            for item in data.get("SPCameraDataType", []):
                name = item.get("_name")
                if name:
                    names.append(str(name))
        except Exception:
            pass

    if names:
        return [(idx, names[idx]) for idx in range(len(names))]
    return [(idx, f"Camera {idx}") for idx in range(max_check)]


def choose_mode(initial_camera: int = 0) -> tuple[str | None, int]:
    """Simple keyboard/mouse menu shown before the clean camera feed, with camera selector."""
    title = "Choose effect"
    selected = [None]
    cameras = list_available_cameras(max_check=5)
    cam_indices = [c[0] for c in cameras]
    cam_names = {c[0]: c[1] for c in cameras}
    if initial_camera not in cam_indices:
        cam_indices.insert(0, initial_camera)
        cam_names[initial_camera] = f"Camera {initial_camera}"
    cam_State = [initial_camera]

    buttons = (
        ("normal", "1  NORMAL VANISH", "V sign  /  dissolve (3.6s)", 100),
        ("naruto", "2  NARUTO VANISH", "Palms together  /  log and smoke", 204),
        ("particles", "3  PARTICLES", "V sign  /  wind fragments (2.1s)", 308),
        ("goku", "4  GOKU TELEPORT", "2 fingers on forehead (1s)  /  instant transmission", 412),
    )
    cam_box_top = 524
    cam_box_bot = 602

    def render_menu() -> np.ndarray:
        window = np.zeros((630, 700, 3), dtype=np.uint8)
        window[:] = (26, 29, 34)
        cv2.putText(window, "CHOOSE YOUR VANISH", (68, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (236, 239, 242), 2, cv2.LINE_AA)
        for mode, heading, detail, top in buttons:
            cv2.rectangle(window, (65, top), (635, top + 88), (48, 54, 62), -1, cv2.LINE_AA)
            cv2.rectangle(window, (65, top), (635, top + 88), (111, 142, 153), 2, cv2.LINE_AA)
            cv2.putText(window, heading, (90, top + 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.72, (240, 245, 247), 2, cv2.LINE_AA)
            cv2.putText(window, detail, (90, top + 64),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.49, (179, 195, 201), 1, cv2.LINE_AA)

        # Camera selector button at the bottom
        cv2.rectangle(window, (65, cam_box_top), (635, cam_box_bot), (36, 46, 56), -1, cv2.LINE_AA)
        cv2.rectangle(window, (65, cam_box_top), (635, cam_box_bot), (95, 190, 220), 2, cv2.LINE_AA)
        cur_idx = cam_State[0]
        cur_name = cam_names.get(cur_idx, f"Camera {cur_idx}")
        # Keep only ASCII characters for cv2.putText compatibility
        safe_name = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in cur_name)[:32]
        cam_label = f"C  CAMERA: [{cur_idx}] {safe_name}"
        cv2.putText(window, cam_label, (90, cam_box_top + 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (130, 230, 255), 2, cv2.LINE_AA)
        cv2.putText(window, "Click here or press C (or Cmd+Shift+C anytime) to switch camera",
                    (90, cam_box_top + 59),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (175, 195, 205), 1, cv2.LINE_AA)
        return window

    def cycle_menu_camera() -> None:
        pos = (cam_indices.index(cam_State[0]) + 1) % len(cam_indices)
        cam_State[0] = cam_indices[pos]

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONUP and 65 <= x <= 635:
            for mode, _, _, top in buttons:
                if top <= y <= top + 88:
                    selected[0] = mode
                    return
            if cam_box_top <= y <= cam_box_bot:
                cycle_menu_camera()

    cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(title, on_mouse)
    try:
        while selected[0] is None:
            cv2.imshow(title, render_menu())
            key = cv2.waitKey(30) & 0xFF
            if key == ord("1"):
                selected[0] = "normal"
            elif key == ord("2"):
                selected[0] = "naruto"
            elif key == ord("3"):
                selected[0] = "particles"
            elif key == ord("4"):
                selected[0] = "goku"
            elif key in (ord("c"), ord("C"), 9):  # C or Tab cycles camera
                cycle_menu_camera()
            elif key in (ord("q"), 27):
                return None, cam_State[0]
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                return None, cam_State[0]
        return selected[0], cam_State[0]
    finally:
        cv2.destroyWindow(title)


def open_virtual_camera(args: argparse.Namespace, width: int, height: int):
    if args.virtual_camera is False:
        return None
    try:
        import pyvirtualcam

        camera = pyvirtualcam.Camera(
            width=width, height=height, fps=args.fps,
            fmt=pyvirtualcam.PixelFormat.BGR,
            backend=args.virtual_backend, device=args.virtual_device,
        )
    except (ImportError, RuntimeError, OSError, ValueError) as error:
        message = (
            "Virtual camera not available. Install OBS Studio (with its "
            "OBS Virtual Camera) or Unity Capture. If you use OBS Virtual Camera, "
            "make sure 'Start Virtual Camera' is stopped in OBS. "
            f"Details: {error}"
        )
        if args.virtual_camera is True or args.virtual_backend or args.virtual_device:
            raise RuntimeError(message) from error
        log(message)
        log("Continuing with the local preview only.")
        return None
    log(f"Virtual camera on: {camera.device} ({width}x{height}, max {args.fps:g} FPS)")
    return camera


def send_virtual_frame(camera, frame: np.ndarray) -> None:
    if frame.shape[:2] != (camera.height, camera.width):
        frame = cv2.resize(frame, (camera.width, camera.height), interpolation=cv2.INTER_LINEAR)
    camera.send(np.ascontiguousarray(frame))


def download_models(mode: str = "normal") -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for destination, url in MODEL_URLS.items():
        if mode in ("naruto", "goku") and destination == GESTURE_MODEL:
            continue
        if mode != "goku" and destination == FACE_MODEL:
            continue
        if destination.exists() and destination.stat().st_size > 50_000:
            continue

        temporary = destination.with_suffix(destination.suffix + ".part")
        log(f"Downloading {destination.name}...")
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Vanish-Lab/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                received = 0
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 256):
                        output.write(chunk)
                        received += len(chunk)
                        if total:
                            percent = int(received * 100 / total)
                            print(f"\r  {percent:3d}%", end="", flush=True)
            print()
            os.replace(temporary, destination)
        except (OSError, urllib.error.URLError) as error:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                "Could not download the MediaPipe models. "
                "Check your internet connection and try again."
            ) from error


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    if platform.system() == "Windows":
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            capture = cv2.VideoCapture(index)
    else:
        capture = cv2.VideoCapture(index)

    if not capture.isOpened():
        raise RuntimeError(
            f"Webcam {index} not available. Close other apps using it or try --camera 1."
        )

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


class GokuPoseRecognizer:
    """Detect Goku's two-finger forehead pose using BlazeFace + HandLandmarker."""

    def __init__(self, face_detector, hand_primary, hand_alternate):
        self.face_detector = face_detector
        self.hand_primary = hand_primary
        self.hand_alternate = hand_alternate
        self.last_hand_count = 0
        self.last_face_detected = False
        self.last_forehead: tuple[float, float, float] | None = None
        self.last_forehead_ms = -10_000

    def recognize_forehead_pose(
        self, image: mp.Image, timestamp_ms: int, mask: np.ndarray | None = None
    ) -> bool:
        face_res = self.face_detector.detect_for_video(image, timestamp_ms)
        forehead = estimate_forehead_from_detections(
            face_res.detections, image.width, image.height
        )
        if forehead is not None:
            self.last_forehead = forehead
            self.last_forehead_ms = timestamp_ms
            self.last_face_detected = True
        elif timestamp_ms - self.last_forehead_ms <= 650:
            forehead = self.last_forehead
            self.last_face_detected = True
        else:
            self.last_face_detected = False

        hand_res = self.hand_primary.detect_for_video(image, timestamp_ms)
        self.last_hand_count = len(hand_res.hand_landmarks)
        if goku_forehead_pose_from_landmarks(
            hand_res.hand_landmarks, forehead, image.width, image.height, mask=mask
        ):
            return True

        # Fallback upper-frame crop in IMAGE mode when hand is near forehead
        if forehead is not None and self.hand_alternate is not None:
            rgb = image.numpy_view()
            h, w = rgb.shape[:2]
            fx, fy, radius = forehead
            crop_left = max(0, int(fx - radius * 2.2))
            crop_right = min(w, int(fx + radius * 2.2))
            crop_top = max(0, int(fy - radius * 1.8))
            crop_bot = min(h, int(fy + radius * 2.8))
            if crop_right - crop_left >= 64 and crop_bot - crop_top >= 64:
                sub_rgb = np.ascontiguousarray(rgb[crop_top:crop_bot, crop_left:crop_right])
                sub_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=sub_rgb)
                alt_res = self.hand_alternate.detect(sub_img)
                self.last_hand_count = max(self.last_hand_count, len(alt_res.hand_landmarks))
                sub_forehead = (fx - crop_left, fy - crop_top, radius)
                if goku_forehead_pose_from_landmarks(
                    alt_res.hand_landmarks,
                    sub_forehead,
                    sub_img.width,
                    sub_img.height,
                    mask=None,
                ):
                    return True
        return False

    def close(self) -> None:
        try:
            self.face_detector.close()
        finally:
            try:
                self.hand_primary.close()
            finally:
                if self.hand_alternate is not None:
                    self.hand_alternate.close()


def create_tasks(
    mode: str = "normal",
) -> tuple[vision.ImageSegmenter, MultiViewGestureRecognizer | MultiViewHandLandmarker | GokuPoseRecognizer]:
    segmenter_options = vision.ImageSegmenterOptions(
        base_options=python.BaseOptions(model_asset_path=str(SEGMENTER_MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    if mode == "goku":
        if not HAND_MODEL.is_file():
            raise RuntimeError(f"Hand model not found: {HAND_MODEL}")
        if not FACE_MODEL.is_file():
            raise RuntimeError(f"Face model not found: {FACE_MODEL}")
        face_options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=str(FACE_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.45,
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(HAND_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.32,
            min_hand_presence_confidence=0.32,
            min_tracking_confidence=0.40,
        )
        segmenter = vision.ImageSegmenter.create_from_options(segmenter_options)
        try:
            face_detector = vision.FaceDetector.create_from_options(face_options)
            try:
                hand_primary = vision.HandLandmarker.create_from_options(hand_options)
                try:
                    hand_alt = vision.HandLandmarker.create_from_options(
                        replace(hand_options, running_mode=vision.RunningMode.IMAGE)
                    )
                except Exception:
                    hand_primary.close()
                    raise
            except Exception:
                face_detector.close()
                raise
        except Exception:
            segmenter.close()
            raise
        return segmenter, GokuPoseRecognizer(face_detector, hand_primary, hand_alt)

    if mode == "naruto":
        if not HAND_MODEL.is_file():
            raise RuntimeError(f"Hand model not found: {HAND_MODEL}")
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(HAND_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.45,
        )
        task_class = vision.HandLandmarker
        wrapper_class = MultiViewHandLandmarker
    else:
        classifier_options = mp.tasks.components.processors.ClassifierOptions(
            score_threshold=0.55,
            category_allowlist=["Victory"],
        )
        options = vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(model_asset_path=str(GESTURE_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.5,
            canned_gesture_classifier_options=classifier_options,
        )
        task_class = vision.GestureRecognizer
        wrapper_class = MultiViewGestureRecognizer

    segmenter = vision.ImageSegmenter.create_from_options(segmenter_options)
    try:
        primary = task_class.create_from_options(options)
        try:
            alternate = task_class.create_from_options(
                replace(options, running_mode=vision.RunningMode.IMAGE)
            )
        except Exception:
            primary.close()
            raise
    except Exception:
        segmenter.close()
        raise
    return segmenter, wrapper_class(primary, alternate)


def smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    values = np.clip((values - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return values * values * (3.0 - 2.0 * values)


def ease_in_out_cubic(value: float) -> float:
    if value < 0.5:
        return 4.0 * value * value * value
    return 1.0 - ((-2.0 * value + 2.0) ** 3) / 2.0


def make_dissolve_fields(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7391)
    y, x = np.mgrid[0:height, 0:width]
    y_normal = y.astype(np.float32) / max(height - 1, 1)
    x_normal = x.astype(np.float32) / max(width - 1, 1)
    low_noise = rng.random((max(2, height // 10), max(2, width // 10)), dtype=np.float32)
    low_noise = cv2.resize(low_noise, (width, height), interpolation=cv2.INTER_CUBIC)
    fine_noise = rng.random((height, width), dtype=np.float32)
    field = (
        (1.0 - y_normal) * 0.72
        + low_noise * 0.17
        + fine_noise * 0.08
        + np.sin(x_normal * 18.0) * 0.025
    )
    return np.clip(field, 0.0, 1.0), fine_noise


def person_mask(
    segmenter: vision.ImageSegmenter,
    image: mp.Image,
    timestamp_ms: int,
    width: int,
    height: int,
) -> np.ndarray:
    result = segmenter.segment_for_video(image, timestamp_ms)
    if not result.confidence_masks:
        return np.zeros((height, width), dtype=np.float32)
    raw = np.squeeze(result.confidence_masks[0].numpy_view()).astype(np.float32)
    resized = cv2.resize(raw, (width, height), interpolation=cv2.INTER_LINEAR)
    resized = cv2.GaussianBlur(resized, (0, 0), sigmaX=2.2, sigmaY=2.2)
    return np.clip((resized - 0.12) / 0.68, 0.0, 1.0)


def alpha_composite(person: np.ndarray, background: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    alpha_3 = alpha[:, :, None]
    return (
        person.astype(np.float32) * alpha_3
        + background.astype(np.float32) * (1.0 - alpha_3)
    ).astype(np.uint8)


def apply_dissolve(
    frame: np.ndarray,
    background: np.ndarray,
    mask: np.ndarray,
    progress: float,
    field: np.ndarray,
    sparkle_noise: np.ndarray,
) -> np.ndarray:
    if progress <= 0.002:
        return alpha_composite(frame, background, mask)
    if progress >= 0.999:
        return background.copy()

    points = cv2.findNonZero((mask > 0.01).astype(np.uint8))
    if points is None:
        return background.copy()
    x, y, width, height = cv2.boundingRect(points)
    left, top = max(0, x - 18), max(0, y - 18)
    right = min(mask.shape[1], x + width + 18)
    bottom = min(mask.shape[0], y + height + 18)
    area = np.s_[top:bottom, left:right]
    mask = mask[area]
    field = field[area]
    sparkle_noise = sparkle_noise[area]
    eased = ease_in_out_cubic(progress)
    survival = smoothstep(eased - 0.055, eased + 0.055, field)
    alpha = mask * survival
    output = alpha_composite(frame[area], background[area], alpha)
    edge = (
        (np.abs(field - eased) < 0.018)
        & (mask > 0.48)
        & (sparkle_noise > 0.54)
    ).astype(np.float32)
    glow = cv2.GaussianBlur(edge, (0, 0), sigmaX=5.0, sigmaY=5.0)
    glow = np.clip(glow * 5.0 + edge, 0.0, 1.0)[:, :, None]
    cyan = np.full_like(output, (255, 228, 92), dtype=np.uint8)
    result = np.clip(
        output.astype(np.float32) * (1.0 - glow * 0.8)
        + cyan.astype(np.float32) * glow * 0.8,
        0,
        255,
    ).astype(np.uint8)
    canvas = background.copy()
    canvas[area] = result
    return canvas


def victory_landmark_score(points: np.ndarray) -> float:
    """Riconosci indice e medio distesi usando distanze 3D, non l'orientamento."""
    if points.shape != (21, 3) or not np.isfinite(points).all():
        return 0.0

    straightness = []
    extended = []
    folded = []
    lengths = []
    # MCP, PIP, DIP e punta: indice, medio, anulare, mignolo.
    for index, base in enumerate((5, 9, 13, 17)):
        finger = points[base : base + 4]
        length = float(np.linalg.norm(np.diff(finger, axis=0), axis=1).sum())
        if length < 1e-6:
            if index < 2:
                return 0.0
            straightness.append(0.0)
            lengths.append(0.0)
            extended.append(False)
            folded.append(True)
            continue
        ratio = float(np.linalg.norm(finger[3] - finger[0])) / length
        tip_distance = float(np.linalg.norm(finger[3] - points[0]))
        joint_distance = float(np.linalg.norm(finger[1] - points[0]))
        straightness.append(ratio)
        lengths.append(length)
        extended.append(ratio >= 0.82 and tip_distance > joint_distance * 1.10)
        folded.append(ratio < 0.78 or tip_distance <= joint_distance * 1.05)

    reference_length = min(lengths[:2])
    for index, base in ((2, 13), (3, 17)):
        reach = float(np.linalg.norm(points[base + 3] - points[base]))
        folded[index] = folded[index] or reach < reference_length * 0.65
    if not (extended[0] and extended[1] and folded[2] and folded[3]):
        return 0.0
    separation = float(np.linalg.norm(points[8] - points[12]))
    if separation < min(lengths[:2]) * 0.20:
        return 0.0
    return float(np.clip(min(straightness[:2]), 0.0, 1.0))


def classify_gesture_result(
    result: vision.GestureRecognizerResult,
    image: mp.Image,
) -> tuple[str, float]:
    for landmarks in result.hand_world_landmarks:
        points = np.array([(point.x, point.y, point.z) for point in landmarks])
        score = victory_landmark_score(points)
        if score:
            return "Victory", score
    for landmarks in result.hand_landmarks:
        points = np.array([(point.x * image.width, point.y * image.height, 0.0)
                           for point in landmarks])
        score = victory_landmark_score(points)
        if score:
            return "Victory", score
    for categories in result.gestures:
        for category in categories:
            if category.category_name == "Victory" and category.score >= 0.62:
                return "Victory", float(category.score)
    if result.hand_landmarks or result.hand_world_landmarks:
        return "Hand_Detected", 0.0
    return "No_Hand", 0.0


class MultiViewGestureRecognizer:
    """Riprova la rilevazione su fotogrammi ruotati senza alterare il tracking."""

    def __init__(self, primary, alternate):
        self.primary = primary
        self.alternate = alternate
        self.preferred_rotation: int | None = None
        self.preferred_crop: str | None = None
        self.next_retry_ms = 0
        self.retry_cursor = 0

    def recognize_gesture(self, image: mp.Image, timestamp_ms: int) -> tuple[str, float]:
        result = self.primary.recognize_for_video(image, timestamp_ms)
        best = classify_gesture_result(result, image)
        if best[0] == "Victory":
            self.preferred_rotation = None
            self.preferred_crop = None
            return best
        if timestamp_ms < self.next_retry_ms:
            return best

        rgb = image.numpy_view()
        height, width = rgb.shape[:2]
        crops = {
            "full": rgb,
            "lower_left": rgb[int(height * 0.28):, :int(width * 0.78)],
            "lower_right": rgb[int(height * 0.28):, int(width * 0.22):],
        }
        views = [("full", rotation) for rotation in (0, 1, 3, 2)]
        views += [(crop, rotation) for crop in ("lower_left", "lower_right")
                  for rotation in (0, 1, 3)]
        preferred = (self.preferred_crop, self.preferred_rotation)
        selected = []
        if preferred in views:
            selected.append(preferred)
        while len(selected) < 3:
            view = views[self.retry_cursor % len(views)]
            self.retry_cursor += 1
            if view not in selected:
                selected.append(view)
        for crop, rotation in selected:
            rotated = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(np.rot90(crops[crop], rotation)),
            )
            result = self.alternate.recognize(rotated)
            candidate = classify_gesture_result(result, rotated)
            if candidate[0] == "Victory":
                self.preferred_rotation = rotation
                self.preferred_crop = crop
                self.next_retry_ms = timestamp_ms + int(GESTURE_INTERVAL_SECONDS * 1000)
                return candidate
            if candidate[0] == "Hand_Detected":
                best = candidate
        self.preferred_rotation = None
        self.preferred_crop = None
        self.next_retry_ms = timestamp_ms + int(GESTURE_INTERVAL_SECONDS * 1000)
        return best

    def close(self) -> None:
        try:
            self.primary.close()
        finally:
            self.alternate.close()


class MultiViewHandLandmarker:
    """Track two hands in video and retry difficult views with the hand model."""

    def __init__(self, primary, alternate):
        self.primary = primary
        self.alternate = alternate
        self.preferred_view: tuple[str, int] | None = None
        self.next_retry_ms = 0
        self.last_hand_count = 0
        self.retry_cursor = 0

    def recognize_joined_hands(self, image: mp.Image, timestamp_ms: int) -> bool:
        result = self.primary.detect_for_video(image, timestamp_ms)
        self.last_hand_count = len(result.hand_landmarks)
        if joined_hands_from_landmarks(result.hand_landmarks, image.width, image.height):
            self.preferred_view = None
            return True
        if timestamp_ms < self.next_retry_ms:
            return False

        rgb = image.numpy_view()
        height, width = rgb.shape[:2]
        views = {
            "full": rgb,
            "center": rgb[int(height * 0.18):, int(width * 0.12):int(width * 0.88)],
            "lower_left": rgb[int(height * 0.22):, :int(width * 0.78)],
            "lower_right": rgb[int(height * 0.22):, int(width * 0.22):],
        }
        attempts = [("full", rotation) for rotation in (1, 3, 2)]
        attempts += [("center", rotation) for rotation in (0, 1, 3)]
        attempts += [("lower_left", 0), ("lower_right", 0)]
        selected = []
        if self.preferred_view in attempts:
            selected.append(self.preferred_view)
        while len(selected) < 2:
            view = attempts[self.retry_cursor % len(attempts)]
            self.retry_cursor += 1
            if view not in selected:
                selected.append(view)
        for crop, rotation in selected:
            rotated = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(np.rot90(views[crop], rotation)),
            )
            result = self.alternate.detect(rotated)
            self.last_hand_count = max(self.last_hand_count, len(result.hand_landmarks))
            if joined_hands_from_landmarks(result.hand_landmarks, rotated.width, rotated.height):
                self.preferred_view = (crop, rotation)
                self.next_retry_ms = timestamp_ms + 90
                return True
        self.preferred_view = None
        self.next_retry_ms = timestamp_ms + 80
        return False

    def close(self) -> None:
        try:
            self.primary.close()
        finally:
            self.alternate.close()


def recognize_gesture(
    recognizer: MultiViewGestureRecognizer,
    image: mp.Image,
    timestamp_ms: int,
) -> tuple[str, float]:
    if isinstance(recognizer, MultiViewGestureRecognizer):
        return recognizer.recognize_gesture(image, timestamp_ms)
    return classify_gesture_result(recognizer.recognize_for_video(image, timestamp_ms), image)


def start_vanish_on_gesture(state: AppState, name: str, score: float, now: float) -> bool:
    """Avvia la dissolvenza al primo riconoscimento affidabile della V."""
    if state.phase == "ready" and name == "Victory" and score >= 0.62:
        state.phase = "vanishing"
        state.vanish_started = now
        return True
    return False


def start_naruto_on_join(state: AppState, joined: bool, now: float) -> bool:
    if state.phase == "ready" and joined:
        state.phase = "naruto_vanishing"
        state.vanish_started = now
        return True
    return False


def update_goku_gesture_hold(
    state: AppState, pose_active: bool, now: float
) -> bool:
    """Track the 1.0-second Goku forehead pose countdown in terminal without video overlays.

    Returns True when the 1.0-second hold completes while `state.gesture_armed` is True.
    """
    if not pose_active:
        if state.goku_hold_started is not None:
            log("Goku pose released — countdown reset.")
        state.goku_hold_started = None
        state.goku_last_countdown = None
        state.gesture_armed = True
        return False

    if not state.gesture_armed:
        return False

    if state.goku_hold_started is None:
        state.goku_hold_started = now
        state.goku_last_countdown = None
        log("Goku pose detected: hold for 1.0s...")
        return False

    held = now - state.goku_hold_started
    remaining_tenths = max(0, int(np.ceil((GOKU_HOLD_SECONDS - held) * 10.0)))
    # Report progress in terminal every ~0.3s
    bucket = remaining_tenths // 3
    if bucket != state.goku_last_countdown and remaining_tenths > 0:
        state.goku_last_countdown = bucket
        log(f"Goku teleport countdown: {remaining_tenths / 10.0:.1f}s...")

    if held >= GOKU_HOLD_SECONDS:
        state.goku_hold_started = None
        state.goku_last_countdown = None
        state.gesture_armed = False
        return True

    return False


def set_fullscreen(enabled: bool) -> None:
    mode = cv2.WINDOW_FULLSCREEN if enabled else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, mode)


def disable_app_nap() -> None:
    """Keep macOS from throttling the loop when the preview is behind other windows."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSProcessInfo
    except ImportError:
        log("Install pyobjc-framework-Cocoa: without it, gestures only work "
            "while the preview window is in front.")
        return
    global _APP_NAP_ACTIVITY
    _APP_NAP_ACTIVITY = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
        0x00FFFFFF | 0xFF00000000, "Live webcam effect"
    )


_APP_NAP_ACTIVITY = None


def self_test() -> int:
    """Check bundled resources and model initialization without opening a webcam."""
    required = (SEGMENTER_MODEL, GESTURE_MODEL, HAND_MODEL, SOUND_PATH, TELEPORT_SOUND_PATH)
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing resources: {', '.join(missing)}")
    load_log()
    import pygame.mixer  # The distributed build must contain its MP3 decoder.
    for mode in ("normal", "naruto", "particles"):
        segmenter, recognizer = create_tasks(mode)
        try:
            recognizer.close()
        finally:
            segmenter.close()
    print("Self-test passed: models, assets and audio are present.")
    return 0


def run() -> int:
    args = parse_args()
    if getattr(args, "self_test", False):
        return self_test()
    if args.mode:
        mode = args.mode
    else:
        mode, chosen_cam = choose_mode(args.camera)
        args.camera = chosen_cam
    if mode is None:
        return 0
    with ExitStack() as resources:
        return run_camera(args, resources, mode)


def run_camera(args: argparse.Namespace, resources: ExitStack, mode: str) -> int:
    download_models(mode)
    disable_app_nap()
    current_camera_index = args.camera
    capture = open_camera(current_camera_index, args.width, args.height)
    resources.callback(lambda: capture.release() if capture is not None else None)
    capture.set(cv2.CAP_PROP_FPS, args.fps)
    segmenter, recognizer = create_tasks(mode)
    resources.callback(segmenter.close)
    resources.callback(recognizer.close)
    log_sprite = load_log() if mode == "naruto" else None
    if mode == "naruto":
        effect_sound = VanishSound(SOUND_PATH)
    elif mode == "goku":
        effect_sound = VanishSound(TELEPORT_SOUND_PATH)
    else:
        effect_sound = None
    if effect_sound is not None:
        resources.callback(effect_sound.close)
    hotkey_monitor = GlobalHotkeyMonitor()
    resources.callback(hotkey_monitor.close)
    resources.callback(_DESKTOP_TOAST.close)
    resources.callback(cv2.destroyAllWindows)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, args.width, args.height)

    init_now = time.perf_counter()
    state = AppState(
        calibration_started=init_now, fullscreen=args.fullscreen
    )
    show_toast(
        state,
        "Capturing background: step out of the frame for 10 seconds.",
        init_now,
        HUD_TOAST_SECONDS,
    )
    if state.fullscreen:
        set_fullscreen(True)

    background: np.ndarray | None = None
    background_samples: list[np.ndarray] = []
    last_mask: np.ndarray | None = None
    last_mask_at = float("-inf")
    dissolve_field: np.ndarray | None = None
    sparkle_noise: np.ndarray | None = None
    log_anchor: tuple[int, int, int] | None = None
    reappear_anchor: tuple[int, int, int] | None = None
    log_cache: dict[int, np.ndarray] = {}
    particle_system: ParticleSystem | None = None
    goku_captured_person: np.ndarray | None = None
    goku_captured_mask: np.ndarray | None = None
    vanished_frame: np.ndarray | None = None
    virtual_camera = None
    virtual_camera_initialized = False
    calibration_remaining = None
    last_gesture_report = 0.0
    started = time.perf_counter()
    log(f"Started in {mode} mode.")
    if mode == "goku":
        log("Keys: Command+Shift+T (or T) gesture ON/OFF, Command+Shift+C (or C) switch camera, SPACE/W new background, F fullscreen, Q quit.")
    else:
        log("Keys: Command+Shift+T (or T) gesture ON/OFF, Command+Shift+C (or C) switch camera, SPACE/W new background, R reappear, V vanish, F fullscreen, Q quit.")
    log("Capturing background: step out of the frame for 10 seconds.")

    gesture_interval = 0.06 if mode == "goku" else (0.08 if mode == "naruto" else GESTURE_INTERVAL_SECONDS)

    try:
        while True:
            ok, camera_frame = capture.read()
            if not ok:
                raise RuntimeError("The webcam stopped sending images.")

            if not args.no_mirror:
                camera_frame = cv2.flip(camera_frame, 1)

            height, width = camera_frame.shape[:2]
            if not virtual_camera_initialized:
                virtual_camera = open_virtual_camera(args, width, height)
                virtual_camera_initialized = True
                if virtual_camera is not None:
                    resources.callback(virtual_camera.close)
            if mode == "normal" and (dissolve_field is None or dissolve_field.shape != (height, width)):
                dissolve_field, sparkle_noise = make_dissolve_fields(height, width)
            now = time.perf_counter()

            # Check global hotkey Command+Shift+T once background calibration is complete
            if state.phase != "calibrating" and hotkey_monitor.poll():
                toggle_gesture_detection(state, now)

            switch_cam_requested = hotkey_monitor.poll_camera_switch()

            elapsed_ms = int((now - started) * 1000)
            mp_image = None
            reappear_now = False

            if state.phase == "calibrating":
                elapsed = now - state.calibration_started
                remaining = max(0, int(np.ceil(CALIBRATION_SECONDS - elapsed)))
                if remaining != calibration_remaining:
                    if remaining:
                        log(f"Capturing background... {remaining}")
                    calibration_remaining = remaining
                if elapsed >= CALIBRATION_SECONDS - BACKGROUND_SAMPLE_SECONDS:
                    background_samples.append(camera_frame.copy())
                if elapsed >= CALIBRATION_SECONDS:
                    if background_samples:
                        stack = np.stack(background_samples[-18:], axis=0)
                        background = np.median(stack, axis=0).astype(np.uint8)
                    else:
                        background = camera_frame.copy()
                    background_samples.clear()
                    state.phase = "ready"
                    state.gesture_detection_enabled = False
                    log("Background captured. Gesture recognition is OFF (full FPS). Press Command+Shift+T (or T) to start/stop gesture recognition.")
                display = camera_frame

            elif background is None:
                state.phase = "calibrating"
                state.calibration_started = now
                display = camera_frame

            elif state.phase == "vanished":
                if vanished_frame is None:
                    vanished_frame = background.copy()
                    if mode == "naruto" and log_anchor is not None:
                        overlay_log(vanished_frame, log_sprite, landed_log_anchor(log_anchor, height),
                                    cache=log_cache)
                display = vanished_frame
                if (
                    state.gesture_detection_enabled
                    and now - state.last_gesture_check >= gesture_interval
                ):
                    state.last_gesture_check = now
                    rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    if mode in ("normal", "particles"):
                        name, score = recognize_gesture(recognizer, mp_image, elapsed_ms)
                        seen = name == "Victory" and score >= 0.62
                        if not seen:
                            state.gesture_armed = True
                        elif state.gesture_armed:
                            reappear_now = True
                    elif mode == "naruto":
                        seen = recognizer.recognize_joined_hands(mp_image, elapsed_ms)
                        if not seen:
                            state.gesture_armed = True
                        elif state.gesture_armed:
                            reappear_now = True
                    elif mode == "goku":
                        pose_ok = recognizer.recognize_forehead_pose(mp_image, elapsed_ms, mask=last_mask)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(
                                f"[Goku] face={recognizer.last_face_detected}, "
                                f"hands={recognizer.last_hand_count}, pose={pose_ok}"
                            )
                            last_gesture_report = now
                        if update_goku_gesture_hold(state, pose_ok, now):
                            reappear_now = True

            else:
                mask = last_mask
                if (
                    state.phase == "ready"
                    and state.gesture_detection_enabled
                    and now - state.last_gesture_check >= gesture_interval
                ):
                    state.last_gesture_check = now
                    rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    if mode in ("normal", "particles"):
                        name, score = recognize_gesture(recognizer, mp_image, elapsed_ms)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(
                                f"[Gesture] {name}, score={score:.2f}, "
                                f"crop={recognizer.preferred_crop or 'full'}, "
                                f"rotation={recognizer.preferred_rotation or 0}"
                            )
                            last_gesture_report = now
                        if not (name == "Victory" and score >= 0.62):
                            state.gesture_armed = True
                        elif state.gesture_armed and start_vanish_on_gesture(state, name, score, now):
                            state.gesture_armed = False
                            if mode == "particles":
                                state.phase = "particles_vanishing"
                                particle_system = None
                                log("Vanished (Particles V sign).")
                            else:
                                log("Vanished (V sign).")
                    elif mode == "naruto":
                        joined = recognizer.recognize_joined_hands(mp_image, elapsed_ms)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(f"[Hands] detected={recognizer.last_hand_count}, "
                                  f"joined={joined}, view={recognizer.preferred_view or 'full'}")
                            last_gesture_report = now
                        if not joined:
                            state.gesture_armed = True
                        elif state.gesture_armed and start_naruto_on_join(state, joined, time.perf_counter()):
                            state.gesture_armed = False
                            log("Vanished (palms together).")
                            effect_sound.play()
                    elif mode == "goku":
                        pose_ok = recognizer.recognize_forehead_pose(mp_image, elapsed_ms, mask=last_mask)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(
                                f"[Goku] face={recognizer.last_face_detected}, "
                                f"hands={recognizer.last_hand_count}, pose={pose_ok}"
                            )
                            last_gesture_report = now
                        if update_goku_gesture_hold(state, pose_ok, now):
                            state.phase = "goku_vanishing"
                            state.vanish_started = time.perf_counter()
                            goku_captured_person = None
                            goku_captured_mask = None
                            log("Instant Transmission! Vanished (Goku pose).")
                            effect_sound.play()

                if state.phase in (
                    "vanishing", "naruto_vanishing", "particles_vanishing",
                    "goku_vanishing", "reappearing",
                ):
                    needs_mask = (
                        (mode == "normal" and (mask is None or now - last_mask_at >= 0.05))
                        or (mode == "naruto" and state.phase == "naruto_vanishing"
                            and (log_anchor is None or now - state.vanish_started < 0.13))
                        or (mode == "naruto" and state.phase == "reappearing"
                            and (mask is None or now - state.vanish_started < 0.25))
                        or (mode == "particles" and particle_system is None)
                        or (mode == "goku" and state.phase == "goku_vanishing" and goku_captured_mask is None)
                        or (mode == "goku" and state.phase == "reappearing"
                            and (mask is None or now - last_mask_at >= 0.05))
                    )
                    if needs_mask:
                        if mp_image is None:
                            rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                        mask = person_mask(segmenter, mp_image, elapsed_ms, width, height)
                        last_mask = mask
                        last_mask_at = now
                    if mode == "naruto" and state.phase == "naruto_vanishing" and log_anchor is None:
                        log_anchor = substitution_anchor(mask)
                    if mode == "particles" and particle_system is None and mask is not None:
                        particle_system = ParticleSystem(camera_frame, mask)
                    if mode == "goku" and state.phase == "goku_vanishing" and goku_captured_mask is None and mask is not None:
                        goku_captured_person = camera_frame.copy()
                        goku_captured_mask = mask.copy()

                if mode == "naruto" and state.phase == "naruto_vanishing":
                    age = max(0.04, time.perf_counter() - state.vanish_started)
                    display = render_substitution(
                        camera_frame, background, mask, log_sprite, log_anchor, age, log_cache
                    )
                    if age >= EFFECT_SECONDS:
                        state.phase = "vanished"
                        vanished_frame = display
                elif mode == "naruto" and state.phase == "reappearing":
                    age = max(0.0, time.perf_counter() - state.vanish_started)
                    if reappear_anchor is None:
                        reappear_anchor = substitution_anchor(mask)
                    display = render_reappearance(
                        camera_frame, background, mask, log_sprite, log_anchor,
                        reappear_anchor, age, log_cache,
                    )
                    if age >= EFFECT_SECONDS:
                        state.phase = "ready"
                        log_anchor = None
                elif mode == "particles" and state.phase == "particles_vanishing":
                    age = max(0.0, time.perf_counter() - state.vanish_started)
                    display = render_particles(background, particle_system, age, reappearing=False)
                    if age >= PARTICLES_SECONDS:
                        state.phase = "vanished"
                        vanished_frame = background.copy()
                elif mode == "particles" and state.phase == "reappearing":
                    age = max(0.0, time.perf_counter() - state.vanish_started)
                    if particle_system is None and mask is not None:
                        particle_system = ParticleSystem(camera_frame, mask)
                    display = render_particles(
                        background, particle_system, age, reappearing=True, live_frame=camera_frame
                    )
                    if age >= PARTICLES_SECONDS:
                        state.phase = "ready"
                        particle_system = None
                elif mode == "goku" and state.phase == "goku_vanishing":
                    age = max(0.0, time.perf_counter() - state.vanish_started)
                    display = render_goku_teleport(
                        camera_frame, background, mask, age,
                        reappearing=False,
                        captured_person=goku_captured_person,
                        captured_mask=goku_captured_mask,
                    )
                    if age >= GOKU_EFFECT_SECONDS:
                        state.phase = "vanished"
                        vanished_frame = background.copy()
                elif mode == "goku" and state.phase == "reappearing":
                    age = max(0.0, time.perf_counter() - state.vanish_started)
                    display = render_goku_teleport(
                        camera_frame, background, mask, age,
                        reappearing=True,
                    )
                    if age >= GOKU_EFFECT_SECONDS:
                        state.phase = "ready"
                        goku_captured_person = None
                        goku_captured_mask = None
                elif state.phase == "ready":
                    display = camera_frame
                else:
                    progress = 0.0
                    if state.phase == "vanishing" and state.vanish_started is not None:
                        progress = min(
                            1.0, (time.perf_counter() - state.vanish_started) / VANISH_SECONDS
                        )
                        if progress >= 1.0:
                            state.phase = "vanished"
                    elif state.phase == "reappearing":
                        progress = REAPPEAR_START_PROGRESS * max(
                            0.0, 1.0 - (time.perf_counter() - state.vanish_started) / REAPPEAR_SECONDS
                        )
                        if progress <= 0.0:
                            state.phase = "ready"
                    display = apply_dissolve(
                        camera_frame, background, mask, progress, dissolve_field, sparkle_noise
                    )
                    if state.phase == "vanished":
                        vanished_frame = display

            update_desktop_toast(state, now)
            if virtual_camera is not None:
                send_virtual_frame(virtual_camera, display if args.no_mirror else cv2.flip(display, 1))
            cv2.imshow(WINDOW_NAME, display)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                log("Quit.")
                break
            if key in (ord("c"), ord("C")) or switch_cam_requested:
                # Cycle through camera indices 0..4 until a working camera opens
                switched = False
                for offset in range(1, 6):
                    candidate_idx = (current_camera_index + offset) % 5
                    try:
                        new_cap = open_camera(candidate_idx, args.width, args.height)
                    except RuntimeError:
                        continue
                    ok_test, _ = new_cap.read()
                    if not ok_test:
                        new_cap.release()
                        continue
                    capture.release()
                    capture = new_cap
                    capture.set(cv2.CAP_PROP_FPS, args.fps)
                    current_camera_index = candidate_idx
                    switched = True
                    break
                if switched:
                    state.phase = "calibrating"
                    state.calibration_started = now
                    state.vanish_started = None
                    state.gesture_detection_enabled = False
                    state.goku_hold_started = None
                    state.goku_last_countdown = None
                    log_anchor = None
                    particle_system = None
                    goku_captured_person = None
                    goku_captured_mask = None
                    last_mask = None
                    last_mask_at = float("-inf")
                    vanished_frame = None
                    background_samples.clear()
                    calibration_remaining = None
                    msg = f"Switched to Camera {current_camera_index}. Capturing background for 10s..."
                    log(msg)
                    show_toast(state, msg, now, HUD_TOAST_SECONDS)
                else:
                    msg = f"No other available camera found (staying on Camera {current_camera_index})."
                    log(msg)
                    show_toast(state, msg, now, HUD_TOAST_SECONDS)
            elif key in (ord("t"), ord("T")) and state.phase != "calibrating":
                toggle_gesture_detection(state, now)
            elif key in (ord(" "), ord("w")):
                state.phase = "calibrating"
                state.calibration_started = now
                state.vanish_started = None
                state.gesture_detection_enabled = False
                state.goku_hold_started = None
                state.goku_last_countdown = None
                log_anchor = None
                particle_system = None
                goku_captured_person = None
                goku_captured_mask = None
                last_mask = None
                last_mask_at = float("-inf")
                vanished_frame = None
                background_samples.clear()
                calibration_remaining = None
                log("Capturing a new background: step out of the frame for 10 seconds.")
                show_toast(
                    state,
                    "Capturing background: step out of the frame for 10 seconds.",
                    now,
                    HUD_TOAST_SECONDS,
                )
            elif (key == ord("r") and mode != "goku") or reappear_now:
                if background is not None:
                    if state.phase not in ("ready", "calibrating"):
                        log("Reappeared (gesture)." if reappear_now else "Reappeared (R key).")
                    if state.phase == "vanished":
                        state.phase = "reappearing"
                        state.vanish_started = time.perf_counter()
                        reappear_anchor = None
                        particle_system = None
                        if mode in ("naruto", "goku") and effect_sound is not None:
                            effect_sound.play()
                    else:
                        state.phase = "ready"
                        state.vanish_started = None
                        log_anchor = None
                        particle_system = None
                    state.gesture_armed = False
                    vanished_frame = None
                    last_mask = None
                    last_mask_at = float("-inf")
            elif key == ord("v") and mode != "goku" and background is not None:
                if mode == "naruto":
                    state.phase = "naruto_vanishing"
                elif mode == "particles":
                    state.phase = "particles_vanishing"
                    particle_system = None
                else:
                    state.phase = "vanishing"
                state.vanish_started = time.perf_counter()
                log("Vanished (V key).")
                if mode == "naruto" and effect_sound is not None:
                    effect_sound.play()
                    log_anchor = None
                vanished_frame = None
            elif key == ord("f"):
                state.fullscreen = not state.fullscreen
                set_fullscreen(state.fullscreen)
            if virtual_camera is not None:
                virtual_camera.sleep_until_next_frame()
    finally:
        resources.close()

    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"\n[Vanish] ERROR: {error}", file=sys.stderr)
        if sys.platform == "darwin":
            safe_err = str(error).replace("\\", "\\\\").replace('"', '\\"')
            try:
                subprocess.run(
                    ["/usr/bin/osascript", "-e", f'display alert "VanishCam Error" message "{safe_err}" as critical'],
                    check=False,
                )
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())