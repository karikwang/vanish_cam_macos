"""Goku Instant Transmission (Shunkan Ido) gesture recognition and comic-line teleport effect."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


GOKU_HOLD_SECONDS = 1.0
GOKU_EFFECT_SECONDS = 0.52
TELEPORT_SOUND_PATH = Path(__file__).resolve().parent / "assets" / "teleport.MP3"


def estimate_forehead_from_detections(
    detections: list[Any], width: int, height: int
) -> tuple[float, float, float] | None:
    """Estimate forehead center (x, y) and acceptance radius in pixels from BlazeFace detections."""
    if not detections:
        return None

    best_det = None
    best_area = -1.0
    for det in detections:
        bbox = getattr(det, "bounding_box", None)
        if bbox is None:
            continue
        area = float(bbox.width * bbox.height)
        if area > best_area:
            best_area = area
            best_det = det

    if best_det is None:
        return None

    bbox = best_det.bounding_box
    bx = float(bbox.origin_x)
    by = float(bbox.origin_y)
    bw = float(bbox.width)
    bh = float(bbox.height)

    keypoints = getattr(best_det, "keypoints", None)
    if keypoints and len(keypoints) >= 2:
        # BlazeFace keypoints 0 and 1 are right eye and left eye (normalized [0, 1])
        ex0, ey0 = float(keypoints[0].x) * width, float(keypoints[0].y) * height
        ex1, ey1 = float(keypoints[1].x) * width, float(keypoints[1].y) * height
        eye_cx = (ex0 + ex1) * 0.5
        eye_cy = (ey0 + ey1) * 0.5
        eye_dist = float(np.hypot(ex1 - ex0, ey1 - ey0))

        # Vector perpendicular to the eye line pointing upward toward the forehead
        dx, dy = ex1 - ex0, ey1 - ey0
        up_x, up_y = -dy, dx
        if up_y > 0:
            up_x, up_y = -up_x, -up_y
        norm = max(1e-6, float(np.hypot(up_x, up_y)))
        up_x /= norm
        up_y /= norm

        offset = max(eye_dist * 0.72, bh * 0.22)
        fx = eye_cx + up_x * offset
        fy = eye_cy + up_y * offset
        radius = max(bw, bh) * 0.55
        return fx, fy, radius

    # Bounding-box fallback if keypoints are missing
    fx = bx + bw * 0.5
    fy = by + bh * 0.20
    radius = max(bw, bh) * 0.55
    return fx, fy, radius


def two_fingers_together_score(points: np.ndarray) -> tuple[bool, np.ndarray | None, float]:
    """Check if index and middle fingers are straight and held together (or close).

    Returns (is_valid, fingertip_midpoint_xy, hand_length).
    """
    if points.shape != (21, 2) and points.shape != (21, 3):
        return False, None, 0.0
    if not np.isfinite(points).all():
        return False, None, 0.0

    pts2d = points[:, :2]
    wrist = pts2d[0]

    lengths = []
    extended = []
    folded = []

    for idx, base in enumerate((5, 9, 13, 17)):
        finger = pts2d[base : base + 4]
        seg_len = float(np.linalg.norm(np.diff(finger, axis=0), axis=1).sum())
        if seg_len < 1e-4:
            if idx < 2:
                return False, None, 0.0
            lengths.append(0.0)
            extended.append(False)
            folded.append(True)
            continue

        direct = float(np.linalg.norm(finger[3] - finger[0]))
        ratio = direct / seg_len
        tip_dist = float(np.linalg.norm(finger[3] - wrist))
        pip_dist = float(np.linalg.norm(finger[1] - wrist))
        mcp_dist = float(np.linalg.norm(finger[0] - wrist))

        lengths.append(seg_len)
        # Index and middle must be reasonably straight and extended away from wrist
        extended.append(ratio >= 0.72 and tip_dist > max(pip_dist * 1.04, mcp_dist * 1.15))
        # Ring and pinky are folded (or occluded when touching forehead)
        folded.append(ratio < 0.82 or tip_dist <= pip_dist * 1.12)

    ref_len = max(1e-4, min(lengths[:2]))
    for idx, base in ((2, 13), (3, 17)):
        reach = float(np.linalg.norm(pts2d[base + 3] - pts2d[base]))
        folded[idx] = folded[idx] or reach < ref_len * 0.72

    if not (extended[0] and extended[1]):
        return False, None, 0.0

    # At least one of ring/pinky should be folded, or index+middle clearly longer than ring+pinky
    ring_tip_dist = float(np.linalg.norm(pts2d[16] - wrist))
    index_tip_dist = float(np.linalg.norm(pts2d[8] - wrist))
    middle_tip_dist = float(np.linalg.norm(pts2d[12] - wrist))
    if not (folded[2] or folded[3] or ring_tip_dist < min(index_tip_dist, middle_tip_dist) * 0.90):
        return False, None, 0.0

    # Index tip (8) and middle tip (12) must be together (side-by-side), not wide apart
    tip_sep = float(np.linalg.norm(pts2d[8] - pts2d[12]))
    pip_sep = float(np.linalg.norm(pts2d[6] - pts2d[10]))
    if tip_sep > ref_len * 0.58 or pip_sep > ref_len * 0.55:
        return False, None, 0.0

    midpoint = (pts2d[8] + pts2d[12]) * 0.5
    return True, midpoint, ref_len


def goku_forehead_pose_from_landmarks(
    hands: list[Any],
    forehead: tuple[float, float, float] | None,
    width: int,
    height: int,
    mask: np.ndarray | None = None,
) -> bool:
    """Return True if a hand has index+middle fingers straight & together against the forehead."""
    if not hands:
        return False

    # Fallback forehead estimate from person silhouette mask if face detector missed a frame
    if forehead is None and mask is not None:
        pts = cv2.findNonZero((mask > 0.45).astype(np.uint8))
        if pts is not None:
            x, y, w, h = cv2.boundingRect(pts)
            forehead = (x + w * 0.5, y + h * 0.14, max(w * 0.45, h * 0.22))

    if forehead is None:
        return False

    fx, fy, radius = forehead
    target = np.array([fx, fy], dtype=np.float32)

    for hand in hands:
        if len(hand) < 21:
            continue
        pts = np.array([(p.x * width, p.y * height) for p in hand[:21]], dtype=np.float32)
        valid, tip_mid, finger_len = two_fingers_together_score(pts)
        if not valid or tip_mid is None:
            continue

        # Check if fingertips or DIP joints are within forehead acceptance zone
        dip_mid = (pts[7] + pts[11]) * 0.5
        dist_tip = float(np.linalg.norm(tip_mid - target))
        dist_dip = float(np.linalg.norm(dip_mid - target))
        allowed = max(radius, finger_len * 0.85)
        if min(dist_tip, dist_dip) <= allowed:
            return True

    return False


def render_goku_teleport(
    frame: np.ndarray,
    background: np.ndarray,
    mask: np.ndarray,
    age: float,
    reappearing: bool = False,
    captured_person: np.ndarray | None = None,
    captured_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Render Dragon Ball style Instant Transmission vertical comic speed lines.

    On disappearance (`reappearing=False`):
      - 0.00..0.22s: vertical comic speed lines streak across the silhouette while person flickers.
      - 0.22..0.52s: person vanishes and speed lines linger briefly on the empty background.
    On reappearance (`reappearing=True`):
      - 0.00..0.24s: vertical comic speed lines appear on the empty background at the target spot.
      - 0.24..0.52s: person snaps back in with lingering comic lines that quickly clear.
    """
    use_person = captured_person if captured_person is not None else frame
    use_mask = captured_mask if captured_mask is not None else mask

    progress = float(np.clip(age / max(GOKU_EFFECT_SECONDS, 1e-6), 0.0, 1.0))
    if progress >= 1.0:
        return frame.copy() if reappearing else background.copy()

    # Determine person visibility alpha with high-frequency anime teleport flicker
    if not reappearing:
        if progress < 0.38:
            # Rapid comic flicker before vanishing
            flicker = 0.25 if int(progress * 32) % 2 == 1 else 0.92
            person_opacity = flicker * (1.0 - (progress / 0.38) * 0.45)
        else:
            person_opacity = 0.0
    else:
        if progress < 0.42:
            person_opacity = 0.0
        elif progress < 0.78:
            flicker = 0.95 if int(progress * 32) % 2 == 0 else 0.30
            person_opacity = flicker
        else:
            person_opacity = 1.0

    if person_opacity <= 0.001:
        output = background.copy()
    elif person_opacity >= 0.999 and reappearing:
        output = frame.copy()
    else:
        alpha = (use_mask * person_opacity)[:, :, None]
        output = (
            use_person.astype(np.float32) * alpha
            + background.astype(np.float32) * (1.0 - alpha)
        ).astype(np.uint8)

    # Find bounding box of silhouette to draw animated vertical comic-style speed lines
    binary = (use_mask > 0.25).astype(np.uint8)
    points = cv2.findNonZero(binary)
    if points is None:
        return output

    bx, by, bw, bh = cv2.boundingRect(points)
    if bw < 8 or bh < 8:
        return output

    # Line intensity peaks around the moment of teleportation (progress ~ 0.38)
    peak = 0.38 if not reappearing else 0.42
    if progress <= peak:
        line_intensity = float(np.clip(progress / max(peak, 1e-6), 0.15, 1.0))
    else:
        line_intensity = float(np.clip(1.0 - (progress - peak) / max(1.0 - peak, 1e-6), 0.0, 1.0))

    if line_intensity <= 0.02:
        return output

    # Horizontal squeeze toward center as the teleport completes/starts
    dist_from_peak = abs(progress - peak)
    width_factor = float(np.clip(1.0 - max(0.0, (progress - peak) * 0.85) if not reappearing else 0.35 + 0.65 * min(1.0, progress / max(peak, 1e-6)), 0.22, 1.0))

    tick = int(age * 60.0)
    rng = np.random.default_rng(4099 + tick * 131)

    overlay = output.copy()
    cx = bx + bw * 0.5
    half_w = (bw * 0.52) * width_factor

    num_lines = max(14, int((bw / 7.5) * line_intensity))
    for i in range(num_lines):
        # Cluster more lines near the center of the silhouette
        rel_x = rng.normal(0.0, 0.42)
        rel_x = float(np.clip(rel_x, -1.0, 1.0))
        lx = int(np.clip(cx + rel_x * half_w, bx, bx + bw - 1))

        # Check vertical span inside or near the silhouette at this column
        col_mask = use_mask[by : by + bh, lx]
        active_y = np.where(col_mask > 0.20)[0]
        if len(active_y) < 4:
            col_top = by + int(bh * 0.1)
            col_bot = by + int(bh * 0.9)
        else:
            col_top = by + int(active_y[0])
            col_bot = by + int(active_y[-1])

        span = max(12, col_bot - col_top)
        seg_len = int(span * rng.uniform(0.22, 0.78) * (0.45 + 0.55 * line_intensity))
        y_start = int(rng.uniform(col_top - span * 0.08, max(col_top, col_bot - seg_len + span * 0.08)))
        y1 = int(np.clip(y_start, 0, output.shape[0] - 1))
        y2 = int(np.clip(y_start + seg_len, 0, output.shape[0] - 1))
        if y2 <= y1 + 2:
            continue

        # Classic Dragon Ball manga/anime speed lines: sharp dark ink lines + bright white/cyan energy streaks
        is_dark = (i % 3 != 0)
        if is_dark:
            color = (18, 20, 24)
            thickness = 1 if rng.random() < 0.55 else 2
        else:
            color = (245, 252, 255)
            thickness = 1 if rng.random() < 0.7 else 2

        cv2.line(overlay, (lx, y1), (lx, y2), color, thickness, cv2.LINE_AA)

    blend_alpha = float(np.clip(line_intensity * 0.92, 0.0, 1.0))
    return cv2.addWeighted(overlay, blend_alpha, output, 1.0 - blend_alpha, 0.0)
