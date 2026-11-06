"""Unit tests for Goku Instant Transmission and Particles modes."""

import unittest
from types import SimpleNamespace
import numpy as np

from goku_effect import (
    GOKU_EFFECT_SECONDS,
    estimate_forehead_from_detections,
    goku_forehead_pose_from_landmarks,
    render_goku_teleport,
    two_fingers_together_score,
)
from particles_effect import PARTICLES_SECONDS, ParticleSystem, render_particles


class GokuEffectTests(unittest.TestCase):
    @staticmethod
    def make_goku_hand(forehead_x=0.5, forehead_y=0.25, spread=0.015):
        """Construct a 21-point normalized hand with index+middle straight together at forehead."""
        pts = [SimpleNamespace(x=forehead_x, y=forehead_y + 0.25) for _ in range(21)]
        pts[0] = SimpleNamespace(x=forehead_x, y=forehead_y + 0.28)
        # Index finger (5..8) straight upward to forehead
        pts[5] = SimpleNamespace(x=forehead_x - spread, y=forehead_y + 0.16)
        pts[6] = SimpleNamespace(x=forehead_x - spread, y=forehead_y + 0.10)
        pts[7] = SimpleNamespace(x=forehead_x - spread, y=forehead_y + 0.05)
        pts[8] = SimpleNamespace(x=forehead_x - spread, y=forehead_y)
        # Middle finger (9..12) straight and parallel next to index
        pts[9] = SimpleNamespace(x=forehead_x + spread, y=forehead_y + 0.16)
        pts[10] = SimpleNamespace(x=forehead_x + spread, y=forehead_y + 0.10)
        pts[11] = SimpleNamespace(x=forehead_x + spread, y=forehead_y + 0.05)
        pts[12] = SimpleNamespace(x=forehead_x + spread, y=forehead_y)
        # Ring (13..16) and pinky (17..20) folded
        for base, offset in ((13, 0.04), (17, 0.07)):
            pts[base] = SimpleNamespace(x=forehead_x + offset, y=forehead_y + 0.17)
            pts[base + 1] = SimpleNamespace(x=forehead_x + offset, y=forehead_y + 0.14)
            pts[base + 2] = SimpleNamespace(x=forehead_x + offset, y=forehead_y + 0.19)
            pts[base + 3] = SimpleNamespace(x=forehead_x + offset, y=forehead_y + 0.22)
        return pts

    def test_forehead_estimation_from_blazeface_detection(self):
        det = SimpleNamespace(
            bounding_box=SimpleNamespace(origin_x=240, origin_y=100, width=160, height=160),
            keypoints=[
                SimpleNamespace(x=0.45, y=0.28),  # right eye
                SimpleNamespace(x=0.55, y=0.28),  # left eye
            ],
        )
        forehead = estimate_forehead_from_detections([det], 640, 480)
        self.assertIsNotNone(forehead)
        fx, fy, radius = forehead
        self.assertAlmostEqual(fx, 320.0, delta=15.0)
        self.assertLess(fy, 0.28 * 480)  # Above the eyes
        self.assertGreater(radius, 40.0)

    def test_two_fingers_together_at_forehead_triggers_but_spread_or_away_does_not(self):
        forehead = (320.0, 120.0, 75.0)
        hand_ok = self.make_goku_hand(0.5, 0.25, spread=0.015)
        self.assertTrue(goku_forehead_pose_from_landmarks([hand_ok], forehead, 640, 480))

        # Wide V-sign (spread fingers) should not count as Goku pose
        hand_wide_v = self.make_goku_hand(0.5, 0.25, spread=0.12)
        self.assertFalse(goku_forehead_pose_from_landmarks([hand_wide_v], forehead, 640, 480))

        # Hand far away from forehead should not trigger
        hand_far = self.make_goku_hand(0.15, 0.75, spread=0.015)
        self.assertFalse(goku_forehead_pose_from_landmarks([hand_far], forehead, 640, 480))

    def test_goku_teleport_renders_vertical_lines_and_finishes_cleanly(self):
        frame = np.full((160, 240, 3), 180, dtype=np.uint8)
        background = np.full_like(frame, 30)
        mask = np.zeros((160, 240), dtype=np.float32)
        mask[25:145, 80:160] = 1.0

        mid_vanish = render_goku_teleport(frame, background, mask, age=0.18, reappearing=False)
        done_vanish = render_goku_teleport(frame, background, mask, age=GOKU_EFFECT_SECONDS, reappearing=False)
        mid_return = render_goku_teleport(frame, background, mask, age=0.22, reappearing=True)
        done_return = render_goku_teleport(frame, background, mask, age=GOKU_EFFECT_SECONDS, reappearing=True)

        self.assertTrue(np.any(mid_vanish != frame))
        self.assertTrue(np.any(mid_vanish != background))
        np.testing.assert_array_equal(done_vanish, background)
        self.assertTrue(np.any(mid_return != background))
        np.testing.assert_array_equal(done_return, frame)


class ParticlesEffectTests(unittest.TestCase):
    def test_particles_drift_and_clear_to_background(self):
        frame = np.full((120, 180, 3), 210, dtype=np.uint8)
        background = np.full_like(frame, 25)
        mask = np.zeros((120, 180), dtype=np.float32)
        mask[20:100, 50:110] = 1.0

        system = ParticleSystem(frame, mask)
        self.assertGreater(len(system.base_x), 50)

        mid = render_particles(background, system, age=0.8, reappearing=False)
        end = render_particles(background, system, age=PARTICLES_SECONDS, reappearing=False)
        self.assertTrue(np.any(mid != background))
        np.testing.assert_array_equal(end, background)


if __name__ == "__main__":
    unittest.main()
