"""Particles mode: silhouette breaks into small colored fragments that drift sideways."""

from __future__ import annotations

import cv2
import numpy as np


PARTICLES_SECONDS = 2.1


class ParticleSystem:
    """Pre-sampled colored fragments from the captured person silhouette."""

    def __init__(self, frame: np.ndarray, mask: np.ndarray, seed: int = 2026):
        height, width = mask.shape[:2]
        self.height = height
        self.width = width
        rng = np.random.default_rng(seed)

        # Sample silhouette on a small grid of fragments (3x3 px blocks)
        step = max(2, min(4, min(height, width) // 130))
        self.radius = max(1, step // 2 + 1)

        ys, xs = np.mgrid[0:height:step, 0:width:step]
        sub_mask = mask[ys, xs]
        valid = sub_mask > 0.35

        self.base_y = ys[valid].astype(np.float32)
        self.base_x = xs[valid].astype(np.float32)
        self.colors = frame[ys[valid], xs[valid]].copy()

        count = len(self.base_x)
        if count == 0:
            self.delays = np.empty(0, dtype=np.float32)
            self.vx = np.empty(0, dtype=np.float32)
            self.vy = np.empty(0, dtype=np.float32)
            self.turb_freq = np.empty(0, dtype=np.float32)
            self.turb_phase = np.empty(0, dtype=np.float32)
            return

        # Stagger release times from top/windward side so silhouette peels away smoothly
        norm_x = (self.base_x - self.base_x.min()) / max(1.0, float(self.base_x.max() - self.base_x.min()))
        norm_y = (self.base_y - self.base_y.min()) / max(1.0, float(self.base_y.max() - self.base_y.min()))
        jitter = rng.uniform(0.0, 0.28, size=count).astype(np.float32)
        self.delays = np.clip((1.0 - norm_x) * 0.25 + norm_y * 0.22 + jitter, 0.0, 0.58).astype(np.float32)

        # Wind velocity drifting sideways (rightward and slightly upward/fluttering)
        self.vx = (width * rng.uniform(0.28, 0.68, size=count)).astype(np.float32)
        self.vy = (height * rng.uniform(-0.18, 0.08, size=count)).astype(np.float32)
        self.turb_freq = rng.uniform(4.5, 9.5, size=count).astype(np.float32)
        self.turb_phase = rng.uniform(0.0, 6.28, size=count).astype(np.float32)


def render_particles(
    background: np.ndarray,
    system: ParticleSystem,
    age: float,
    reappearing: bool = False,
    live_frame: np.ndarray | None = None,
) -> np.ndarray:
    """Render colored silhouette fragments drifting in the wind."""
    progress = float(np.clip(age / max(PARTICLES_SECONDS, 1e-6), 0.0, 1.0))
    if reappearing:
        progress = 1.0 - progress

    if progress >= 1.0:
        return background.copy()
    if progress <= 0.0 and reappearing and live_frame is not None:
        return live_frame.copy()

    output = background.copy()
    if len(system.base_x) == 0:
        return output

    # Local particle age after its staggered release delay
    local_t = np.clip((progress - system.delays) / np.maximum(1e-4, 1.0 - system.delays), 0.0, 1.0)
    alive = local_t < 0.98
    if not np.any(alive):
        return output

    t = local_t[alive]
    bx = system.base_x[alive]
    by = system.base_y[alive]
    vx = system.vx[alive]
    vy = system.vy[alive]
    freq = system.turb_freq[alive]
    phase = system.turb_phase[alive]
    colors = system.colors[alive]

    # Accelerating wind drift + sinusoidal flutter
    drift_t = t * t * 1.35 + t * 0.35
    px = np.rint(bx + vx * drift_t).astype(np.int32)
    flutter = np.sin(t * freq + phase) * (system.height * 0.025 * t)
    py = np.rint(by + vy * drift_t + flutter).astype(np.int32)

    # Fade alpha as fragments drift further
    alpha = np.clip(1.0 - (t ** 1.6), 0.0, 1.0)[:, None]

    in_bounds = (px >= 0) & (px < system.width) & (py >= 0) & (py < system.height)
    px = px[in_bounds]
    py = py[in_bounds]
    colors = colors[in_bounds]
    alpha = alpha[in_bounds]

    # Render fragments with slight size expansion for smooth coverage
    r = system.radius
    for dy in range(-r + 1, r):
        for dx in range(-r + 1, r):
            ny = np.clip(py + dy, 0, system.height - 1)
            nx = np.clip(px + dx, 0, system.width - 1)
            bg_pixels = output[ny, nx].astype(np.float32)
            output[ny, nx] = np.clip(
                colors.astype(np.float32) * alpha + bg_pixels * (1.0 - alpha),
                0,
                255,
            ).astype(np.uint8)

    return output
