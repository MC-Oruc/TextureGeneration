from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from texture_generation.common.image_writer import write_tga
from texture_generation.generators.wet_water_surface import (
    WaterSurfaceSettings,
    evaluate_normal,
    generate,
    generate_modes,
)
from texture_generation.generators.wet_ripple_impacts import (
    RippleImpactSettings,
    generate as generate_impacts,
)
from texture_generation.common.models import GenerationContext


class WaterSurfaceTests(unittest.TestCase):
    def test_modes_are_deterministic_and_seeded(self) -> None:
        first = generate_modes(WaterSurfaceSettings(seed=401))
        second = generate_modes(WaterSurfaceSettings(seed=401))
        different = generate_modes(WaterSurfaceSettings(seed=402))
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_surface_loops_in_space_and_time(self) -> None:
        settings = WaterSurfaceSettings(seed=401)
        modes = generate_modes(settings)
        start = evaluate_normal(modes, settings, 0.31, 0.67, 0.0)
        time_end = evaluate_normal(modes, settings, 0.31, 0.67, 1.0)
        u_end = evaluate_normal(modes, settings, 1.31, 0.67, 0.0)
        v_end = evaluate_normal(modes, settings, 0.31, 1.67, 0.0)
        for expected, actual in zip(start, time_end):
            self.assertAlmostEqual(expected, actual, places=10)
        for expected, actual in zip(start, u_end):
            self.assertAlmostEqual(expected, actual, places=10)
        for expected, actual in zip(start, v_end):
            self.assertAlmostEqual(expected, actual, places=10)

    def test_macro_modes_are_balanced_counter_wave_pairs(self) -> None:
        settings = WaterSurfaceSettings(seed=401)
        modes = generate_modes(settings)
        macro_modes = modes[: settings.macro_mode_count]
        for forward, counter in zip(macro_modes[::2], macro_modes[1::2]):
            self.assertEqual(forward.cycles_x, counter.cycles_x)
            self.assertEqual(forward.cycles_y, counter.cycles_y)
            self.assertEqual(forward.temporal_cycles, -counter.temporal_cycles)
            self.assertEqual(forward.spatial_phase, counter.spatial_phase)
            self.assertEqual(forward.temporal_phase, counter.temporal_phase)

    def test_small_atlas_and_tga_output(self) -> None:
        settings = WaterSurfaceSettings(
            frame_resolution=12,
            frames_per_axis=2,
            gutter_pixels=1,
            macro_mode_count=2,
            micro_mode_count=2,
        )
        output = generate(GenerationContext(Path(".")), settings)[0]
        self.assertEqual(output.width, 24)
        self.assertEqual(output.height, 24)
        self.assertEqual(len(output.rgba8), 24 * 24 * 4)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.tga"
            write_tga(path, output.width, output.height, output.rgba8)
            self.assertEqual(path.read_bytes()[2], 2)
            self.assertEqual(path.stat().st_size, 18 + 24 * 24 * 4)

    def test_impact_generator_packs_two_seeded_outputs(self) -> None:
        settings = RippleImpactSettings(
            frame_resolution=12,
            frames_per_axis=2,
            gutter_pixels=1,
            puddle_event_count=2,
            wet_film_event_count=2,
        )
        outputs = generate_impacts(GenerationContext(Path(".")), settings)
        self.assertEqual(
            [output.asset_name for output in outputs],
            ["T_WetRippleAtlas_A_Packed", "T_WetRippleAtlas_B_Packed"],
        )
        self.assertNotEqual(outputs[0].rgba8, outputs[1].rgba8)
        self.assertEqual(len(outputs[0].rgba8), 24 * 24 * 4)


if __name__ == "__main__":
    unittest.main()
