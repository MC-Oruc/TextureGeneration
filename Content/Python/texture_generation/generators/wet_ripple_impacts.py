from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..common.models import GenerationContext, TextureOutput

TAU = math.tau


@dataclass(frozen=True)
class RippleImpactSettings:
    frame_resolution: int = 128
    frames_per_axis: int = 8
    gutter_pixels: int = 4
    tile_size_cm: float = 180.0
    cycle_seconds: float = 2.133333
    puddle_event_count: int = 18
    puddle_min_radius_cm: float = 14.0
    puddle_max_radius_cm: float = 26.0
    puddle_min_lifetime_seconds: float = 0.65
    puddle_max_lifetime_seconds: float = 1.25
    wet_film_event_count: int = 30
    wet_film_min_radius_cm: float = 3.5
    wet_film_max_radius_cm: float = 9.0
    wet_film_min_lifetime_seconds: float = 0.18
    wet_film_max_lifetime_seconds: float = 0.42
    crest_width_cm: float = 1.8
    trough_strength: float = 0.38
    edge_irregularity: float = 0.14
    normal_strength: float = 0.62
    seed_a: int = 1729
    seed_b: int = 7919


@dataclass(frozen=True)
class SurfaceBand:
    event_count: int
    min_radius_cm: float
    max_radius_cm: float
    min_lifetime_seconds: float
    max_lifetime_seconds: float
    strength_scale: float


@dataclass(frozen=True)
class ImpactEvent:
    position_x: float
    position_y: float
    birth: float
    lifetime: float
    max_radius_cm: float
    amplitude: float
    shape_phase: float
    axis_ratio: float
    rotation: float


def _smooth_unit(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _wrap_signed(value: float) -> float:
    return value - math.floor(value + 0.5)


def _generate_events(
    rng: random.Random,
    band: SurfaceBand,
    cycle_seconds: float,
) -> list[ImpactEvent]:
    return [
        ImpactEvent(
            position_x=rng.random(),
            position_y=rng.random(),
            birth=rng.random(),
            lifetime=max(
                0.01,
                min(
                    0.95,
                    rng.uniform(band.min_lifetime_seconds, band.max_lifetime_seconds)
                    / cycle_seconds,
                ),
            ),
            max_radius_cm=rng.uniform(band.min_radius_cm, band.max_radius_cm),
            amplitude=rng.uniform(0.72, 1.18) * band.strength_scale,
            shape_phase=rng.uniform(0.0, TAU),
            axis_ratio=rng.uniform(0.88, 1.12),
            rotation=rng.uniform(0.0, TAU),
        )
        for _ in range(band.event_count)
    ]


def _evaluate_gradient(
    events: list[ImpactEvent],
    settings: RippleImpactSettings,
    u: float,
    v: float,
    time: float,
) -> tuple[float, float]:
    gradient_x = 0.0
    gradient_y = 0.0

    for event in events:
        elapsed = (time - event.birth) % 1.0
        if elapsed >= event.lifetime:
            continue

        age = elapsed / event.lifetime
        expansion = _smooth_unit(age)
        fade_in = _smooth_unit(age / 0.08)
        fade_out = max(1.0 - age, 0.0) ** 1.45
        envelope = fade_in * fade_out * event.amplitude

        delta_x = _wrap_signed(u - event.position_x) * settings.tile_size_cm
        delta_y = _wrap_signed(v - event.position_y) * settings.tile_size_cm
        cos_rotation = math.cos(event.rotation)
        sin_rotation = math.sin(event.rotation)
        ellipse_x = cos_rotation * delta_x + sin_rotation * delta_y
        ellipse_y = (
            -sin_rotation * delta_x + cos_rotation * delta_y
        ) / event.axis_ratio
        distance = max(math.hypot(ellipse_x, ellipse_y), 0.001)
        angle = math.atan2(ellipse_y, ellipse_x)

        edge_noise = (
            math.sin(angle * 3.0 + event.shape_phase) * 0.58
            + math.sin(angle * 7.0 - event.shape_phase * 1.71) * 0.29
            + math.sin(angle * 11.0 + event.shape_phase * 0.43) * 0.13
        )
        radius = (
            event.max_radius_cm
            * expansion
            * (1.0 + edge_noise * settings.edge_irregularity)
        )
        width = settings.crest_width_cm * (0.82 + (1.35 - 0.82) * age)
        crest_distance = (distance - radius) / max(width, 0.1)
        crest = math.exp(-(crest_distance * crest_distance))
        trough_radius = max(radius - width * 1.85, 0.0)
        trough_distance = (distance - trough_radius) / max(width * 1.45, 0.1)
        trough = (
            math.exp(-(trough_distance * trough_distance))
            * settings.trough_strength
        )
        wave = (crest - trough) * envelope

        inverse_distance = 1.0 / math.hypot(delta_x, delta_y) if delta_x or delta_y else 0.0
        gradient_x += delta_x * inverse_distance * wave
        gradient_y += delta_y * inverse_distance * wave

    return gradient_x, gradient_y


def _encode_normal(
    gradient: tuple[float, float],
    strength: float,
) -> tuple[int, int]:
    normal_x = -gradient[0] * strength
    normal_y = -gradient[1] * strength
    inverse_length = 1.0 / math.sqrt(normal_x * normal_x + normal_y * normal_y + 1.0)
    encoded_x = max(0.0, min(1.0, normal_x * inverse_length * 0.5 + 0.5))
    encoded_y = max(0.0, min(1.0, normal_y * inverse_length * 0.5 + 0.5))
    return round(encoded_x * 255.0), round(encoded_y * 255.0)


def _validate_settings(settings: RippleImpactSettings) -> None:
    if settings.frame_resolution < 8 or settings.frames_per_axis < 2:
        raise ValueError("Atlas dimensions are below supported limits.")
    if settings.gutter_pixels < 1 or settings.gutter_pixels * 2 >= settings.frame_resolution:
        raise ValueError("Gutter must leave a positive frame interior.")
    if settings.tile_size_cm <= 0.0 or settings.cycle_seconds <= 0.0:
        raise ValueError("Tile size and cycle duration must be positive.")
    if settings.puddle_min_radius_cm > settings.puddle_max_radius_cm:
        raise ValueError("Puddle radius range is invalid.")
    if settings.wet_film_min_radius_cm > settings.wet_film_max_radius_cm:
        raise ValueError("Wet-film radius range is invalid.")


def _generate_atlas(settings: RippleImpactSettings, seed: int) -> bytearray:
    _validate_settings(settings)
    puddle_band = SurfaceBand(
        settings.puddle_event_count,
        settings.puddle_min_radius_cm,
        settings.puddle_max_radius_cm,
        settings.puddle_min_lifetime_seconds,
        settings.puddle_max_lifetime_seconds,
        1.0,
    )
    wet_film_band = SurfaceBand(
        settings.wet_film_event_count,
        settings.wet_film_min_radius_cm,
        settings.wet_film_max_radius_cm,
        settings.wet_film_min_lifetime_seconds,
        settings.wet_film_max_lifetime_seconds,
        0.72,
    )
    rng = random.Random(seed)
    puddle_events = _generate_events(rng, puddle_band, settings.cycle_seconds)
    wet_film_events = _generate_events(rng, wet_film_band, settings.cycle_seconds)

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
                puddle_normal = _encode_normal(
                    _evaluate_gradient(puddle_events, settings, u, v, time),
                    settings.normal_strength,
                )
                wet_film_normal = _encode_normal(
                    _evaluate_gradient(wet_film_events, settings, u, v, time),
                    settings.normal_strength,
                )
                atlas_x = frame_x * settings.frame_resolution + local_x
                pixel = (atlas_y * atlas_size + atlas_x) * 4
                pixels[pixel] = puddle_normal[0]
                pixels[pixel + 1] = puddle_normal[1]
                pixels[pixel + 2] = wet_film_normal[0]
                pixels[pixel + 3] = wet_film_normal[1]
    return pixels


def generate(
    context: GenerationContext,
    settings: RippleImpactSettings | None = None,
) -> list[TextureOutput]:
    del context
    settings = settings or RippleImpactSettings()
    atlas_size = settings.frame_resolution * settings.frames_per_axis
    texture_settings = {
        "srgb": False,
        "compression_settings": ("TextureCompressionSettings", "TC_BC7"),
        "compression_no_alpha": False,
        "mip_gen_settings": ("TextureMipGenSettings", "TMGS_SHARPEN1"),
        "lod_group": ("TextureGroup", "TEXTUREGROUP_EFFECTS"),
        "address_x": ("TextureAddress", "TA_CLAMP"),
        "address_y": ("TextureAddress", "TA_CLAMP"),
        "filter": ("TextureFilter", "TF_BILINEAR"),
        "oodle_preserve_extremes": True,
    }
    return [
        TextureOutput(
            asset_name="T_WetRippleAtlas_A_Packed",
            width=atlas_size,
            height=atlas_size,
            rgba8=_generate_atlas(settings, settings.seed_a),
            texture_settings=texture_settings,
        ),
        TextureOutput(
            asset_name="T_WetRippleAtlas_B_Packed",
            width=atlas_size,
            height=atlas_size,
            rgba8=_generate_atlas(settings, settings.seed_b),
            texture_settings=texture_settings,
        ),
    ]
