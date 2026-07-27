from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..common.models import GenerationContext, TextureOutput

TAU = math.tau


@dataclass(frozen=True)
class WaterSurfaceSettings:
    frame_resolution: int = 128
    frames_per_axis: int = 8
    gutter_pixels: int = 4
    tile_size_cm: float = 180.0
    cycle_seconds: float = 3.2
    macro_mode_count: int = 6
    macro_min_wavelength_cm: float = 55.0
    macro_max_wavelength_cm: float = 90.0
    macro_height_amplitude_cm: float = 0.20
    micro_mode_count: int = 12
    micro_min_wavelength_cm: float = 12.0
    micro_max_wavelength_cm: float = 30.0
    micro_height_amplitude_cm: float = 0.035
    wind_direction_degrees: float = 28.0
    macro_direction_spread_degrees: float = 55.0
    micro_direction_spread_degrees: float = 100.0
    macro_counter_wave_strength: float = 1.0
    normal_strength: float = 1.0
    water_depth_cm: float = 0.7
    seed: int = 104729


@dataclass
class WaveMode:
    cycles_x: int
    cycles_y: int
    temporal_cycles: int
    amplitude_cm: float
    spatial_phase: float
    temporal_phase: float


def _round_unreal(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0.0 else math.ceil(value - 0.5)


def _append_band(
    modes: list[WaveMode],
    rng: random.Random,
    settings: WaterSurfaceSettings,
    mode_count: int,
    minimum_wavelength_cm: float,
    maximum_wavelength_cm: float,
    height_amplitude_cm: float,
    minimum_temporal_cycles: int,
    maximum_temporal_cycles: int,
    direction_spread_degrees: float,
    balanced_counter_waves: bool = False,
) -> None:
    minimum_cycles = max(1, math.ceil(settings.tile_size_cm / maximum_wavelength_cm))
    maximum_cycles = max(
        minimum_cycles,
        math.floor(settings.tile_size_cm / minimum_wavelength_cm),
    )
    first_mode = len(modes)
    weight_squared_sum = 0.0

    source_mode_count = mode_count // 2 if balanced_counter_waves else mode_count
    for _ in range(source_mode_count):
        direction_degrees = (
            settings.wind_direction_degrees
            + rng.uniform(-direction_spread_degrees, direction_spread_degrees)
        )
        direction = math.radians(direction_degrees)
        requested_magnitude = rng.uniform(minimum_cycles, maximum_cycles)
        cycles_x = _round_unreal(math.cos(direction) * requested_magnitude)
        cycles_y = _round_unreal(math.sin(direction) * requested_magnitude)
        if cycles_x == 0 and cycles_y == 0:
            cycles_x = minimum_cycles

        magnitude = math.hypot(cycles_x, cycles_y)
        wavelength_cm = settings.tile_size_cm / max(magnitude, 1.0)
        wave_number_per_meter = TAU / max(wavelength_cm * 0.01, 0.001)
        depth_meters = settings.water_depth_cm * 0.01
        gravity_term = 9.81 * wave_number_per_meter
        capillary_term = 0.000072 * wave_number_per_meter**3
        depth_factor = math.tanh(min(wave_number_per_meter * depth_meters, 10.0))
        angular_frequency = math.sqrt((gravity_term + capillary_term) * depth_factor)
        target_cycles = angular_frequency * settings.cycle_seconds / TAU
        temporal_cycles = min(
            maximum_temporal_cycles,
            max(minimum_temporal_cycles, _round_unreal(target_cycles)),
        )

        amplitude = rng.uniform(0.75, 1.25) / math.sqrt(max(magnitude, 1.0))
        spatial_phase = rng.uniform(0.0, TAU)
        temporal_phase = rng.uniform(0.0, TAU)
        mode = WaveMode(
            cycles_x=cycles_x,
            cycles_y=cycles_y,
            temporal_cycles=temporal_cycles,
            amplitude_cm=amplitude,
            spatial_phase=spatial_phase,
            temporal_phase=temporal_phase,
        )
        modes.append(mode)
        weight_squared_sum += amplitude * amplitude
        if balanced_counter_waves:
            counter_amplitude = amplitude * settings.macro_counter_wave_strength
            modes.append(
                WaveMode(
                    cycles_x=cycles_x,
                    cycles_y=cycles_y,
                    temporal_cycles=-temporal_cycles,
                    amplitude_cm=counter_amplitude,
                    spatial_phase=spatial_phase,
                    temporal_phase=temporal_phase,
                )
            )
            weight_squared_sum += counter_amplitude * counter_amplitude

    amplitude_scale = height_amplitude_cm / math.sqrt(max(weight_squared_sum, 1.0e-8))
    for mode in modes[first_mode:]:
        mode.amplitude_cm *= amplitude_scale


def generate_modes(settings: WaterSurfaceSettings) -> list[WaveMode]:
    _validate_settings(settings)
    rng = random.Random(settings.seed)
    modes: list[WaveMode] = []
    _append_band(
        modes,
        rng,
        settings,
        settings.macro_mode_count,
        settings.macro_min_wavelength_cm,
        settings.macro_max_wavelength_cm,
        settings.macro_height_amplitude_cm,
        1,
        1,
        settings.macro_direction_spread_degrees,
        balanced_counter_waves=True,
    )
    _append_band(
        modes,
        rng,
        settings,
        settings.micro_mode_count,
        settings.micro_min_wavelength_cm,
        settings.micro_max_wavelength_cm,
        settings.micro_height_amplitude_cm,
        2,
        5,
        settings.micro_direction_spread_degrees,
    )
    return modes


def evaluate_normal(
    modes: list[WaveMode],
    settings: WaterSurfaceSettings,
    u: float,
    v: float,
    normalized_time: float,
) -> tuple[float, float]:
    gradient_x = 0.0
    gradient_y = 0.0
    for mode in modes:
        traveling_phase = (
            TAU * (mode.cycles_x * u + mode.cycles_y * v)
            + mode.spatial_phase
            - TAU * mode.temporal_cycles * normalized_time
            + mode.temporal_phase
        )
        gradient_scale = (
            -mode.amplitude_cm
            * TAU
            * math.sin(traveling_phase)
            / settings.tile_size_cm
        )
        gradient_x += gradient_scale * mode.cycles_x
        gradient_y += gradient_scale * mode.cycles_y

    normal_x = -gradient_x * settings.normal_strength
    normal_y = -gradient_y * settings.normal_strength
    inverse_length = 1.0 / math.sqrt(normal_x * normal_x + normal_y * normal_y + 1.0)
    return (
        max(0.0, min(1.0, normal_x * inverse_length * 0.5 + 0.5)),
        max(0.0, min(1.0, normal_y * inverse_length * 0.5 + 0.5)),
    )


def _validate_settings(settings: WaterSurfaceSettings) -> None:
    if settings.frame_resolution < 8 or settings.frames_per_axis < 2:
        raise ValueError("Atlas dimensions are below supported limits.")
    if settings.gutter_pixels < 1 or settings.gutter_pixels * 2 >= settings.frame_resolution:
        raise ValueError("Gutter must leave a positive frame interior.")
    if settings.tile_size_cm <= 0.0 or settings.cycle_seconds <= 0.0:
        raise ValueError("Tile size and cycle duration must be positive.")
    if settings.macro_mode_count < 2 or settings.micro_mode_count < 2:
        raise ValueError("Each wave band requires at least two modes.")
    if settings.macro_mode_count % 2 != 0:
        raise ValueError("Macro wave mode count must be even for balanced counter waves.")
    if not 0.0 <= settings.macro_counter_wave_strength <= 1.0:
        raise ValueError("Macro counter-wave strength must be between zero and one.")


def generate(
    context: GenerationContext,
    settings: WaterSurfaceSettings | None = None,
) -> list[TextureOutput]:
    del context
    settings = settings or WaterSurfaceSettings()
    modes = generate_modes(settings)
    frame_count = settings.frames_per_axis**2
    interior_size = settings.frame_resolution - settings.gutter_pixels * 2
    atlas_size = settings.frame_resolution * settings.frames_per_axis
    pixels = bytearray(atlas_size * atlas_size * 4)

    for frame_index in range(frame_count):
        frame_x = frame_index % settings.frames_per_axis
        frame_y = frame_index // settings.frames_per_axis
        time = frame_index / frame_count
        for local_y in range(settings.frame_resolution):
            v = ((local_y - settings.gutter_pixels + 0.5) / interior_size) % 1.0
            atlas_y = frame_y * settings.frame_resolution + local_y
            for local_x in range(settings.frame_resolution):
                u = ((local_x - settings.gutter_pixels + 0.5) / interior_size) % 1.0
                normal_x, normal_y = evaluate_normal(modes, settings, u, v, time)
                atlas_x = frame_x * settings.frame_resolution + local_x
                pixel = (atlas_y * atlas_size + atlas_x) * 4
                pixels[pixel] = _round_unreal(normal_x * 255.0)
                pixels[pixel + 1] = _round_unreal(normal_y * 255.0)
                pixels[pixel + 2] = 255
                pixels[pixel + 3] = 255

    return [
        TextureOutput(
            asset_name="T_WetWaterSurfaceLoop_N",
            width=atlas_size,
            height=atlas_size,
            rgba8=pixels,
            texture_settings={
                "srgb": False,
                "compression_settings": ("TextureCompressionSettings", "TC_NORMALMAP"),
                "compression_no_alpha": True,
                "mip_gen_settings": ("TextureMipGenSettings", "TMGS_SHARPEN1"),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_EFFECTS"),
                "address_x": ("TextureAddress", "TA_CLAMP"),
                "address_y": ("TextureAddress", "TA_CLAMP"),
                "filter": ("TextureFilter", "TF_BILINEAR"),
                "oodle_preserve_extremes": True,
            },
        )
    ]
