from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from texture_generation.common.image_writer import encode_radiance_hdr, write_tga
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
from texture_generation.generators.wet_city_reflection import (
    WetCityReflectionSettings,
    _default_source_image,
    _balance_horizontal_light_energy,
    _orient_for_unreal_cubemap,
    _spread_horizon_lights,
)
from texture_generation.generators.wet_neutral_surface_defaults import (
    generate as generate_neutral_defaults,
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

    def test_radiance_hdr_output_uses_scanline_rle(self) -> None:
        width = 257
        height = 2
        row = [
            (
                0.05 + index / width,
                0.10 + (index % 17) / 17,
                0.20 + (index % 31) / 31,
            )
            for index in range(width)
        ]
        encoded = encode_radiance_hdr(width, height, [row, row])
        self.assertIn(b"FORMAT=32-bit_rle_rgbe", encoded)
        resolution = b"-Y 2 +X 257\n"
        cursor = encoded.index(resolution) + len(resolution)

        for _row in range(height):
            self.assertEqual(encoded[cursor : cursor + 4], bytes((2, 2, 1, 1)))
            cursor += 4
            for _channel in range(4):
                decoded_width = 0
                while decoded_width < width:
                    packet = encoded[cursor]
                    cursor += 1
                    if packet > 128:
                        decoded_width += packet - 128
                        cursor += 1
                    else:
                        decoded_width += packet
                        cursor += packet
                self.assertEqual(decoded_width, width)
        self.assertEqual(cursor, len(encoded))

    def test_city_reflection_balances_dim_horizontal_sectors(self) -> None:
        width = 32
        height = 16
        pixels = bytearray(width * height * 4)
        for index in range(3, len(pixels), 4):
            pixels[index] = 255
        for y in range(4, 12):
            for x in range(0, 4):
                index = (y * width + x) * 4
                pixels[index : index + 3] = bytes((220, 180, 120))
            for x in range(16, 20):
                index = (y * width + x) * 4
                pixels[index : index + 3] = bytes((80, 70, 60))

        spread = _spread_horizon_lights(
            pixels,
            width,
            height,
            WetCityReflectionSettings(),
        )
        balanced = _balance_horizontal_light_energy(
            spread,
            width,
            height,
            WetCityReflectionSettings(),
        )
        bright_before = sum(pixels[(y * width + x) * 4] for y in range(4, 12) for x in range(4))
        bright_after = sum(balanced[(y * width + x) * 4] for y in range(4, 12) for x in range(4))
        dim_before = sum(pixels[(y * width + x) * 4] for y in range(4, 12) for x in range(16, 20))
        dim_after = sum(balanced[(y * width + x) * 4] for y in range(4, 12) for x in range(16, 20))

        self.assertGreater(dim_after, dim_before)
        self.assertLessEqual(bright_after, bright_before * 1.15)
        self.assertGreater(
            dim_after / dim_before,
            bright_after / bright_before,
        )

    def test_city_reflection_matches_unreal_vertical_orientation(self) -> None:
        top = bytes((255, 0, 0, 255, 0, 255, 0, 255))
        bottom = bytes((0, 0, 255, 255, 255, 255, 255, 255))

        oriented = _orient_for_unreal_cubemap(bytearray(top + bottom), 2, 2)

        self.assertEqual(oriented, bytearray(bottom + top))

    def test_city_reflection_default_source_is_bundled_with_plugin(self) -> None:
        source = _default_source_image()

        self.assertTrue(source.is_file())
        self.assertEqual(source.parts[-4:], ("SourceArt", "Environment", "WetSurface", source.name))


class WetNeutralSurfaceDefaultsTests(unittest.TestCase):
    def test_outputs_are_canonical_solid_defaults(self) -> None:
        outputs = generate_neutral_defaults(GenerationContext(Path(".")))
        expected = {
            "T_WetDefault_BaseColor": (255, 255, 255, 255),
            "T_WetDefault_Normal": (128, 128, 255, 255),
            "T_WetDefault_ORM": (255, 128, 0, 255),
        }
        self.assertEqual([output.asset_name for output in outputs], list(expected))

        for output in outputs:
            self.assertEqual((output.width, output.height), (4, 4))
            payload = bytes(expected[output.asset_name]) * 16
            self.assertEqual(output.rgba8, payload)
            self.assertEqual(output.rgba8[:4], payload[:4])
            self.assertEqual(output.rgba8[-4:], payload[-4:])

        base, normal, orm = outputs
        self.assertTrue(base.texture_settings["srgb"])
        self.assertEqual(base.texture_settings["compression_settings"][1], "TC_DEFAULT")
        self.assertFalse(normal.texture_settings["srgb"])
        self.assertTrue(normal.texture_settings["compression_no_alpha"])
        self.assertEqual(normal.texture_settings["compression_settings"][1], "TC_NORMALMAP")
        self.assertFalse(orm.texture_settings["srgb"])
        self.assertTrue(orm.texture_settings["compression_no_alpha"])
        self.assertEqual(orm.texture_settings["compression_settings"][1], "TC_MASKS")


if __name__ == "__main__":
    unittest.main()
