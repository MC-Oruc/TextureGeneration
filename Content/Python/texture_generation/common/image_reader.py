from __future__ import annotations

import struct
from pathlib import Path


def read_tga_rgba8(path: Path) -> tuple[int, int, bytearray]:
    data = path.read_bytes()
    if len(data) < 18:
        raise ValueError(f"{path} is not a valid TGA file.")

    (
        id_length,
        color_map_type,
        image_type,
        _color_map_origin,
        color_map_length,
        color_map_depth,
        _x_origin,
        _y_origin,
        width,
        height,
        pixel_depth,
        descriptor,
    ) = struct.unpack("<BBBHHBHHHHBB", data[:18])

    if color_map_type != 0 or color_map_length != 0 or color_map_depth != 0:
        raise ValueError("Color-mapped TGA sources are not supported.")
    if image_type != 2 or pixel_depth not in (24, 32):
        raise ValueError("Only uncompressed 24-bit and 32-bit TGA sources are supported.")

    channels = pixel_depth // 8
    offset = 18 + id_length
    expected_size = width * height * channels
    pixels = data[offset : offset + expected_size]
    if len(pixels) != expected_size:
        raise ValueError("TGA pixel payload is truncated.")

    rgba = bytearray(width * height * 4)
    for index in range(width * height):
        source = index * channels
        target = index * 4
        rgba[target] = pixels[source + 2]
        rgba[target + 1] = pixels[source + 1]
        rgba[target + 2] = pixels[source]
        rgba[target + 3] = pixels[source + 3] if channels == 4 else 255

    if not descriptor & 0x20:
        row_size = width * 4
        flipped = bytearray(len(rgba))
        for row in range(height):
            source = row * row_size
            target = (height - row - 1) * row_size
            flipped[target : target + row_size] = rgba[source : source + row_size]
        rgba = flipped

    return width, height, rgba
