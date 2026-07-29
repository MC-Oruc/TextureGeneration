from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..common.models import GenerationContext, TextureOutput


@dataclass(frozen=True)
class WetSurfaceFieldSettings:
    resolution: int = 512
    puddle_octaves: int = 5
    puddle_base_frequency: int = 4
    glint_cells: int = 48
    seed: int = 130363


def _grid(size: int, seed: int) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.random() for _ in range(size)] for _ in range(size)]


def _sample_periodic(grid: list[list[float]], u: float, v: float) -> float:
    size = len(grid)
    x = (u % 1.0) * size
    y = (v % 1.0) * size
    x0 = math.floor(x) % size
    y0 = math.floor(y) % size
    x1 = (x0 + 1) % size
    y1 = (y0 + 1) % size
    tx = x - math.floor(x)
    ty = y - math.floor(y)
    tx = tx * tx * (3.0 - 2.0 * tx)
    ty = ty * ty * (3.0 - 2.0 * ty)
    a = grid[y0][x0] * (1.0 - tx) + grid[y0][x1] * tx
    b = grid[y1][x0] * (1.0 - tx) + grid[y1][x1] * tx
    return a * (1.0 - ty) + b * ty


def _build_octaves(settings: WetSurfaceFieldSettings, seed: int) -> list[list[list[float]]]:
    return [
        _grid(settings.puddle_base_frequency << octave, seed + octave * 7919)
        for octave in range(settings.puddle_octaves)
    ]


def _fbm(grids: list[list[list[float]]], u: float, v: float) -> float:
    value = 0.0
    weight = 0.5
    total = 0.0
    for grid in grids:
        value += _sample_periodic(grid, u, v) * weight
        total += weight
        weight *= 0.5
    return value / total


def _byte(value: float) -> int:
    return max(0, min(255, round(value * 255.0)))


def generate(
    context: GenerationContext,
    **options: object,
) -> list[TextureOutput]:
    settings = WetSurfaceFieldSettings(**options)
    if settings.resolution < 64:
        raise ValueError("resolution must be at least 64.")
    if settings.puddle_octaves < 1:
        raise ValueError("puddle_octaves must be positive.")
    if settings.glint_cells < 4:
        raise ValueError("glint_cells must be at least 4.")

    primary_grids = _build_octaves(settings, settings.seed)
    secondary_grids = _build_octaves(settings, settings.seed + 104729)
    glint_rng = random.Random(settings.seed + 32452843)
    centers = [
        [(glint_rng.random(), glint_rng.random()) for _ in range(settings.glint_cells)]
        for _ in range(settings.glint_cells)
    ]
    selectors = [
        [glint_rng.random() for _ in range(settings.glint_cells)]
        for _ in range(settings.glint_cells)
    ]

    pixels = bytearray(settings.resolution * settings.resolution * 4)
    index = 0
    for y in range(settings.resolution):
        v = y / settings.resolution
        cell_y_float = v * settings.glint_cells
        cell_y = math.floor(cell_y_float) % settings.glint_cells
        local_y = cell_y_float - math.floor(cell_y_float)
        for x in range(settings.resolution):
            u = x / settings.resolution
            primary = _fbm(primary_grids, u, v)
            secondary = _fbm(secondary_grids, u, v)

            cell_x_float = u * settings.glint_cells
            cell_x = math.floor(cell_x_float) % settings.glint_cells
            local_x = cell_x_float - math.floor(cell_x_float)
            center_x, center_y = centers[cell_y][cell_x]
            distance = math.hypot(local_x - center_x, local_y - center_y)
            spot = max(0.0, min(1.0, (0.17 - distance) / 0.13))
            spot = spot * spot * (3.0 - 2.0 * spot)

            pixels[index] = _byte(primary)
            pixels[index + 1] = _byte(secondary)
            pixels[index + 2] = _byte(spot)
            pixels[index + 3] = _byte(selectors[cell_y][cell_x])
            index += 4

    return [
        TextureOutput(
            asset_name="T_WetSurfaceFields_Packed",
            width=settings.resolution,
            height=settings.resolution,
            rgba8=pixels,
            texture_settings={
                "srgb": False,
                "compression_settings": ("TextureCompressionSettings", "TC_BC7"),
                "compression_no_alpha": False,
                "mip_gen_settings": ("TextureMipGenSettings", "TMGS_SHARPEN1"),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_EFFECTS"),
                "address_x": ("TextureAddress", "TA_WRAP"),
                "address_y": ("TextureAddress", "TA_WRAP"),
                "filter": ("TextureFilter", "TF_BILINEAR"),
                "oodle_preserve_extremes": True,
            },
        )
    ]
