from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ..common.image_reader import read_tga_rgba8
from ..common.image_writer import encode_radiance_hdr
from ..common.models import GenerationContext, TextureOutput


@dataclass(frozen=True)
class WetCityReflectionSettings:
    source_image: str | Path | None = None
    seam_width: int = 96
    source_sky_end: float = 0.32
    source_city_end: float = 0.56
    output_sky_end: float = 0.30
    output_city_end: float = 0.70
    base_exposure: float = 3.2
    highlight_threshold: float = 0.012
    highlight_boost: float = 18.0
    light_spread_strength: float = 0.28
    horizon_start: float = 0.47
    horizon_end: float = 0.55
    horizon_spread_radius: int = 96
    horizon_spread_strength: float = 0.42
    sector_count: int = 16
    sector_balance_strength: float = 1.0
    sector_max_gain: float = 12.0


def _default_source_image() -> Path:
    relative = Path("SourceArt/Environment/WetSurface/WetCityReflection_Source.tga")
    try:
        import unreal
    except ImportError:
        return Path.cwd() / relative
    return Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())) / relative


def _srgb_to_linear(value: int) -> float:
    normalized = value / 255.0
    if normalized <= 0.04045:
        return normalized / 12.92
    return ((normalized + 0.055) / 1.055) ** 2.4


def _make_horizontal_seam_continuous(
    rgba8: bytearray,
    width: int,
    height: int,
    seam_width: int,
) -> None:
    extent = min(max(1, seam_width), width // 4)
    for y in range(height):
        for distance in range(extent):
            left = (y * width + distance) * 4
            right = (y * width + width - distance - 1) * 4
            blend = 0.5 * (1.0 - distance / extent)
            for channel in range(3):
                left_value = rgba8[left + channel]
                right_value = rgba8[right + channel]
                rgba8[left + channel] = round(
                    left_value + (right_value - left_value) * blend
                )
                rgba8[right + channel] = round(
                    right_value + (left_value - right_value) * blend
                )


def _remap_environment_band(
    rgba8: bytearray,
    width: int,
    height: int,
    settings: WetCityReflectionSettings,
) -> bytearray:
    remapped = bytearray(len(rgba8))
    for y in range(height):
        vertical = y / max(1, height - 1)
        if vertical <= settings.output_sky_end:
            source_vertical = (
                vertical
                / max(1.0e-6, settings.output_sky_end)
                * settings.source_sky_end
            )
        elif vertical <= settings.output_city_end:
            city_alpha = (
                vertical - settings.output_sky_end
            ) / max(1.0e-6, settings.output_city_end - settings.output_sky_end)
            source_vertical = settings.source_sky_end + city_alpha * (
                settings.source_city_end - settings.source_sky_end
            )
        else:
            lower_alpha = (
                vertical - settings.output_city_end
            ) / max(1.0e-6, 1.0 - settings.output_city_end)
            ambient = (
                round(18 + (6 - 18) * lower_alpha),
                round(22 + (9 - 22) * lower_alpha),
                round(27 + (13 - 27) * lower_alpha),
                255,
            )
            row_start = y * width * 4
            for x in range(width):
                target = row_start + x * 4
                remapped[target : target + 4] = bytes(ambient)
            continue

        source_y = source_vertical * (height - 1)
        source_y0 = int(source_y)
        source_y1 = min(height - 1, source_y0 + 1)
        alpha = source_y - source_y0
        for x in range(width):
            target = (y * width + x) * 4
            source0 = (source_y0 * width + x) * 4
            source1 = (source_y1 * width + x) * 4
            for channel in range(4):
                remapped[target + channel] = round(
                    rgba8[source0 + channel]
                    + (rgba8[source1 + channel] - rgba8[source0 + channel])
                    * alpha
                )
    return remapped


def _preserve_small_lights(
    rgba8: bytearray,
    width: int,
    height: int,
    settings: WetCityReflectionSettings,
) -> bytearray:
    widened = bytearray(rgba8)
    first_row = max(1, round(height * (settings.output_sky_end - 0.04)))
    last_row = min(height - 1, round(height * (settings.output_city_end + 0.02)))

    for y in range(first_row, last_row):
        for x in range(width):
            target = (y * width + x) * 4
            current_luma = max(rgba8[target : target + 3])
            best = target
            best_luma = current_luma

            for sample_y in range(max(0, y - 1), min(height, y + 2)):
                for sample_x in range(max(0, x - 1), min(width, x + 2)):
                    sample = (sample_y * width + sample_x) * 4
                    sample_luma = max(rgba8[sample : sample + 3])
                    if sample_luma > best_luma:
                        best = sample
                        best_luma = sample_luma

            if best_luma < 72 or best_luma <= current_luma + 8:
                continue
            for channel in range(3):
                widened[target + channel] = round(
                    rgba8[target + channel]
                    + (rgba8[best + channel] - rgba8[target + channel])
                    * settings.light_spread_strength
                )
    return widened


def _balance_horizontal_light_energy(
    rgba8: bytearray,
    width: int,
    height: int,
    settings: WetCityReflectionSettings,
) -> bytearray:
    sector_count = max(2, settings.sector_count)
    first_row = max(0, round(height * settings.horizon_start))
    last_row = min(height, round(height * settings.horizon_end))
    energy = [0.0] * sector_count

    for y in range(first_row, last_row):
        for x in range(width):
            index = (y * width + x) * 4
            highlight = max(rgba8[index : index + 3]) - 48
            if highlight > 0:
                sector = min(sector_count - 1, x * sector_count // width)
                energy[sector] += highlight

    lit_energy = sorted(value for value in energy if value > 0.0)
    if not lit_energy:
        return bytearray(rgba8)

    target = lit_energy[round((len(lit_energy) - 1) * 0.75)]
    strength = max(0.0, min(1.0, settings.sector_balance_strength))
    maximum_gain = max(1.0, settings.sector_max_gain)
    gains = [
        1.0
        + (
            min(maximum_gain, target / max(value, target * 0.08)) - 1.0
        )
        * strength
        if value < target
        else 1.0
        for value in energy
    ]

    balanced = bytearray(rgba8)
    for x in range(width):
        position = x * sector_count / width - 0.5
        left = math.floor(position)
        alpha = position - left
        alpha = alpha * alpha * (3.0 - 2.0 * alpha)
        gain = gains[left % sector_count] + (
            gains[(left + 1) % sector_count] - gains[left % sector_count]
        ) * alpha

        for y in range(first_row, last_row):
            index = (y * width + x) * 4
            for channel in range(3):
                value = rgba8[index + channel]
                balanced[index + channel] = min(
                    255,
                    round(min(value, 48) + max(0, value - 48) * gain),
                )
    return balanced


def _spread_horizon_lights(
    rgba8: bytearray,
    width: int,
    height: int,
    settings: WetCityReflectionSettings,
) -> bytearray:
    first_row = max(0, round(height * settings.horizon_start))
    last_row = min(height, round(height * settings.horizon_end))
    radius = max(8, settings.horizon_spread_radius)
    strength = max(0.0, min(1.0, settings.horizon_spread_strength))
    spread = bytearray(rgba8)

    for y in range(first_row, last_row):
        for x in range(width):
            target = (y * width + x) * 4
            current_luma = max(rgba8[target : target + 3])
            best = -1
            best_score = 0.0
            best_blend = 0.0

            for distance in range(8, radius + 1, 8):
                falloff = 1.0 - distance / (radius + 8.0)
                for direction in (-1, 1):
                    sample_x = (x + direction * distance) % width
                    sample = (y * width + sample_x) * 4
                    sample_luma = max(rgba8[sample : sample + 3])
                    score = max(0.0, sample_luma - 72.0) * falloff
                    if score > best_score:
                        best = sample
                        best_score = score
                        best_blend = strength * falloff

            if best < 0 or max(rgba8[best : best + 3]) <= current_luma + 8:
                continue
            for channel in range(3):
                spread[target + channel] = round(
                    rgba8[target + channel]
                    + (rgba8[best + channel] - rgba8[target + channel])
                    * best_blend
                )
    return spread


def _hdr_rows(
    rgba8: bytearray,
    width: int,
    height: int,
    settings: WetCityReflectionSettings,
):
    for y in range(height):
        row: list[tuple[float, float, float]] = []
        for x in range(width):
            index = (y * width + x) * 4
            red = _srgb_to_linear(rgba8[index])
            green = _srgb_to_linear(rgba8[index + 1])
            blue = _srgb_to_linear(rgba8[index + 2])
            luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722
            highlight = max(
                0.0,
                (luminance - settings.highlight_threshold)
                / max(1.0e-6, 1.0 - settings.highlight_threshold),
            )
            exposure = settings.base_exposure + settings.highlight_boost * (
                highlight**1.35
            )
            row.append((red * exposure, green * exposure, blue * exposure))
        yield row


def _orient_for_unreal_cubemap(
    rgba8: bytearray,
    width: int,
    height: int,
) -> bytearray:
    """Match the generated long-lat image to Unreal's cubemap hemisphere convention."""
    stride = width * 4
    oriented = bytearray(len(rgba8))
    for y in range(height):
        source = y * stride
        target = (height - 1 - y) * stride
        oriented[target : target + stride] = rgba8[source : source + stride]
    return oriented


def generate(
    _context: GenerationContext,
    settings: WetCityReflectionSettings | None = None,
    **overrides,
) -> list[TextureOutput]:
    if settings is not None and overrides:
        raise ValueError("Pass settings or keyword overrides, not both.")
    settings = settings or WetCityReflectionSettings(**overrides)
    source_image = Path(settings.source_image) if settings.source_image else _default_source_image()
    width, height, rgba8 = read_tga_rgba8(source_image)

    if width != height * 2:
        raise ValueError("Wet city reflection source must use a 2:1 equirectangular layout.")

    rgba8 = _remap_environment_band(rgba8, width, height, settings)
    rgba8 = _preserve_small_lights(rgba8, width, height, settings)
    rgba8 = _spread_horizon_lights(rgba8, width, height, settings)
    rgba8 = _balance_horizontal_light_energy(rgba8, width, height, settings)
    _make_horizontal_seam_continuous(
        rgba8,
        width,
        height,
        settings.seam_width,
    )
    rgba8 = _orient_for_unreal_cubemap(rgba8, width, height)
    encoded = encode_radiance_hdr(
        width,
        height,
        _hdr_rows(rgba8, width, height, settings),
    )
    return [
        TextureOutput(
            asset_name="T_WetCityReflection_HDR",
            width=width,
            height=height,
            encoded_bytes=encoded,
            source_extension=".hdr",
            texture_settings={
                "srgb": False,
                "compression_settings": ("TextureCompressionSettings", "TC_HDR"),
                "compression_no_alpha": True,
                "mip_gen_settings": (
                    "TextureMipGenSettings",
                    "TMGS_FROM_TEXTURE_GROUP",
                ),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_SKYBOX"),
                "filter": ("TextureFilter", "TF_TRILINEAR"),
            },
        )
    ]
