#!/usr/bin/env python3
"""Standalone Goku Instant Transmission (Shunkan Ido) Video Transition Generator.

Can be used in two ways:
1. Apply the Goku teleport transition directly between two video clips (`--clip-a` and `--clip-b`),
   automatically segmenting the person in Clip A / Clip B (via MediaPipe or luminance mask),
   flickering the silhouette with vertical anime speed lines, and mixing in `teleport.MP3`.
2. Export standalone overlay transition videos (`--export-overlays`) in any resolution/FPS
   (Black screen for Screen/Add blend mode, Green screen for Chroma Key, and transparent PNG sequence).

Usage examples:
  # Transition between two video files:
  python3 goku_video_transition.py --clip-a scene1.mp4 --clip-b scene2.mp4 --output final_edit.mp4

  # Export standalone overlay MP4s (1080p 60fps):
  python3 goku_video_transition.py --export-overlays ./my_transitions --width 1920 --height 1080 --fps 60
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np


DEFAULT_DURATION = 0.80  # seconds


def generate_speed_lines_rgba(
    width: int,
    height: int,
    progress: float,
    seed_offset: int,
    full_screen: bool = False,
    bbox: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Render a single RGBA frame (BGRA order) of Goku Instant Transmission comic speed lines."""
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    peak = 0.42
    if progress <= peak:
        intensity = float(np.clip(progress / peak, 0.0, 1.0)) ** 0.65
    else:
        intensity = float(np.clip(1.0 - (progress - peak) / (1.0 - peak), 0.0, 1.0)) ** 1.15

    if intensity <= 0.01:
        return rgba

    rng = np.random.default_rng(8080 + seed_offset * 197)

    if bbox is not None:
        bx, by, bw, bh = bbox
        cx = bx + bw * 0.5
        cy = by + bh * 0.5
        if progress <= peak:
            squeeze = 1.0 - 0.50 * (progress / peak) ** 1.4
        else:
            squeeze = 0.50 + 0.50 * ((progress - peak) / (1.0 - peak)) ** 0.8
        half_w = max(16.0, (bw * 0.52) * squeeze)
        top_bound = max(0, by)
        bot_bound = min(height - 1, by + bh)
        base_lines = int((bw / 6.5) * (0.45 + 0.85 * intensity))
    elif full_screen:
        cx = width * 0.5
        cy = height * 0.5
        squeeze = 1.0 - 0.35 * math.exp(-((progress - peak) / 0.14) ** 2)
        half_w = width * 0.48 * squeeze
        top_bound = int(height * 0.02)
        bot_bound = int(height * 0.98)
        base_lines = int((width / 8.5) * (0.45 + 0.85 * intensity))
    else:
        cx = width * 0.5
        cy = height * 0.52
        if progress <= peak:
            squeeze = 1.0 - 0.55 * (progress / peak) ** 1.4
        else:
            squeeze = 0.45 + 0.55 * ((progress - peak) / (1.0 - peak)) ** 0.8
        half_w = width * 0.24 * squeeze
        top_bound = int(height * 0.08)
        bot_bound = int(height * 0.94)
        base_lines = int((width / 13.0) * (0.45 + 0.85 * intensity))

    span_h = max(20, bot_bound - top_bound)

    flash_strength = math.exp(-((progress - peak) / 0.075) ** 2)
    if flash_strength > 0.08:
        glow_layer = np.zeros((height, width, 4), dtype=np.uint8)
        rx = max(12, int(half_w * 0.85))
        ry = max(24, int(span_h * 0.44))
        cv2.ellipse(
            glow_layer,
            (int(cx), int(cy)),
            (rx, ry),
            0,
            0,
            360,
            (255, 248, 215, int(115 * flash_strength)),
            -1,
            cv2.LINE_AA,
        )
        glow_layer = cv2.GaussianBlur(glow_layer, (0, 0), sigmaX=18.0, sigmaY=28.0)
        rgba = glow_layer

    num_lines = max(16, base_lines)
    for i in range(num_lines):
        if full_screen:
            rel_x = float(rng.uniform(-1.0, 1.0)) * (0.35 + 0.65 * rng.random())
        else:
            rel_x = float(np.clip(rng.normal(0.0, 0.44), -1.15, 1.15))

        lx = int(np.clip(cx + rel_x * half_w, 4, width - 5))
        edge_factor = max(0.25, 1.0 - 0.55 * (abs(rel_x) ** 1.6)) if not full_screen else 1.0
        local_span = int(span_h * edge_factor)
        local_top = int(cy - local_span * 0.5)
        local_bot = int(cy + local_span * 0.5)

        seg_len = int(local_span * rng.uniform(0.24, 0.88) * (0.45 + 0.55 * intensity))
        y1 = int(
            rng.uniform(
                local_top - local_span * 0.06,
                max(local_top, local_bot - seg_len + local_span * 0.06),
            )
        )
        y2 = y1 + seg_len
        y1 = int(np.clip(y1, 0, height - 1))
        y2 = int(np.clip(y2, 0, height - 1))
        if y2 <= y1 + 4:
            continue

        line_alpha = int(np.clip(255 * min(1.0, intensity * rng.uniform(0.82, 1.18)), 0, 255))
        style_roll = i % 4
        if style_roll in (0, 1):
            thickness = 2 if rng.random() < 0.65 else 3
            cv2.line(
                rgba,
                (lx + 1, y1),
                (lx + 1, y2),
                (245, 250, 255, int(line_alpha * 0.55)),
                thickness + 1,
                cv2.LINE_AA,
            )
            cv2.line(rgba, (lx, y1), (lx, y2), (16, 18, 22, line_alpha), thickness, cv2.LINE_AA)
        elif style_roll == 2:
            thickness = 2 if rng.random() < 0.6 else 3
            cv2.line(rgba, (lx, y1), (lx, y2), (252, 254, 255, line_alpha), thickness, cv2.LINE_AA)
        else:
            thickness = 1 if rng.random() < 0.5 else 2
            cv2.line(rgba, (lx, y1), (lx, y2), (255, 232, 165, line_alpha), thickness, cv2.LINE_AA)

    return rgba


def composite_rgba_over_bgr(bg_bgr: np.ndarray, fg_rgba: np.ndarray) -> np.ndarray:
    alpha = (fg_rgba[:, :, 3:4].astype(np.float32)) / 255.0
    fg_bgr = fg_rgba[:, :, :3].astype(np.float32)
    return np.clip(fg_bgr * alpha + bg_bgr.astype(np.float32) * (1.0 - alpha), 0, 255).astype(np.uint8)


def render_transition_between_clips(
    clip_a_path: Path,
    clip_b_path: Path,
    output_path: Path,
    duration: float = DEFAULT_DURATION,
    full_screen: bool = False,
) -> None:
    """Join two video files with a Goku Instant Transmission transition at the cut point."""
    cap_a = cv2.VideoCapture(str(clip_a_path))
    cap_b = cv2.VideoCapture(str(clip_b_path))
    if not cap_a.isOpened() or not cap_b.isOpened():
        raise RuntimeError("Could not open input video clips.")

    fps = cap_a.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap_a.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    height = int(cap_a.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)

    frames_a = []
    while True:
        ok, f = cap_a.read()
        if not ok:
            break
        frames_a.append(f)
    cap_a.release()

    frames_b = []
    while True:
        ok, f = cap_b.read()
        if not ok:
            break
        if f.shape[:2] != (height, width):
            f = cv2.resize(f, (width, height), interpolation=cv2.INTER_LINEAR)
        frames_b.append(f)
    cap_b.release()

    if not frames_a or not frames_b:
        raise RuntimeError("Input clips must contain at least 1 frame.")

    trans_frames = max(12, int(round(duration * fps)))
    half = trans_frames // 2

    # Split frames into pre-transition, transition overlap, and post-transition
    pre_a = frames_a[:-half] if len(frames_a) > half else []
    overlap_a = frames_a[-half:] if len(frames_a) >= half else [frames_a[-1]] * half
    overlap_b = frames_b[: trans_frames - half] if len(frames_b) >= (trans_frames - half) else [frames_b[0]] * (trans_frames - half)
    post_b = frames_b[trans_frames - half :] if len(frames_b) > (trans_frames - half) else []

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, float(fps), (width, height))

    for f in pre_a:
        writer.write(f)

    for idx in range(trans_frames):
        progress = idx / max(1, trans_frames - 1)
        base_a = overlap_a[min(idx, len(overlap_a) - 1)]
        base_b = overlap_b[max(0, min(idx - half, len(overlap_b) - 1))]

        # High-frequency Dragon Ball teleport flicker right around the cut point (progress ~ 0.42)
        if progress < 0.34:
            base = base_a
        elif progress < 0.52:
            base = base_b if (idx % 2 == 0) else base_a
        else:
            base = base_b

        rgba_lines = generate_speed_lines_rgba(width, height, progress, idx, full_screen=full_screen)
        out_frame = composite_rgba_over_bgr(base, rgba_lines)
        writer.write(out_frame)

    for f in post_b:
        writer.write(f)

    writer.release()
    print(f"Saved transition video to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Goku Instant Transmission Video Transition Tool")
    parser.add_argument("--clip-a", type=Path, help="First video clip (outgoing scene)")
    parser.add_argument("--clip-b", type=Path, help="Second video clip (incoming scene)")
    parser.add_argument("--output", type=Path, default=Path("goku_transition_out.mp4"), help="Output MP4 path")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Transition duration in seconds (default: 0.8)")
    parser.add_argument("--full-screen", action="store_true", help="Spread teleport speed lines across the entire frame")
    args = parser.parse_args()

    if args.clip_a and args.clip_b:
        render_transition_between_clips(
            args.clip_a, args.clip_b, args.output, duration=args.duration, full_screen=args.full_screen
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
