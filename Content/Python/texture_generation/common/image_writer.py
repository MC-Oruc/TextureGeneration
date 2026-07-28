from __future__ import annotations

import math
import struct
from collections.abc import Iterable, Sequence
from pathlib import Path


def write_tga(path: Path, width: int, height: int, rgba8: bytes | bytearray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack(
        "<BBBHHBHHHHBB",
        0,
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        width,
        height,
        32,
        0x28,
    )

    bgra = bytearray(len(rgba8))
    bgra[0::4] = rgba8[2::4]
    bgra[1::4] = rgba8[1::4]
    bgra[2::4] = rgba8[0::4]
    bgra[3::4] = rgba8[3::4]
    path.write_bytes(header + bgra)


def _encode_radiance_channel(values: Sequence[int]) -> bytes:
    encoded = bytearray()
    index = 0

    while index < len(values):
        run_length = 1
        while (
            index + run_length < len(values)
            and run_length < 127
            and values[index + run_length] == values[index]
        ):
            run_length += 1

        if run_length >= 4:
            encoded.extend((128 + run_length, values[index]))
            index += run_length
            continue

        literal_start = index
        index += run_length
        while index < len(values) and index - literal_start < 128:
            next_run = 1
            while (
                index + next_run < len(values)
                and next_run < 4
                and values[index + next_run] == values[index]
            ):
                next_run += 1
            if next_run >= 4:
                break
            index = min(index + next_run, literal_start + 128)

        literal_length = index - literal_start
        encoded.append(literal_length)
        encoded.extend(values[literal_start:index])

    return bytes(encoded)


def _to_rgbe(red: float, green: float, blue: float) -> tuple[int, int, int, int]:
    maximum = max(red, green, blue)
    if maximum < 1.0e-32:
        return 0, 0, 0, 0

    mantissa, exponent = math.frexp(maximum)
    scale = mantissa * 256.0 / maximum
    return (
        min(255, max(0, int(red * scale))),
        min(255, max(0, int(green * scale))),
        min(255, max(0, int(blue * scale))),
        min(255, max(0, exponent + 128)),
    )


def encode_radiance_hdr(
    width: int,
    height: int,
    rows: Iterable[Sequence[tuple[float, float, float]]],
) -> bytes:
    if width < 8 or width > 32767:
        raise ValueError("Radiance scanline RLE requires a width from 8 to 32767.")

    encoded = bytearray(
        f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {height} +X {width}\n".encode("ascii")
    )
    row_count = 0

    for row in rows:
        if len(row) != width:
            raise ValueError("Radiance row width does not match the image width.")
        channels = [bytearray() for _ in range(4)]
        for red, green, blue in row:
            for channel, value in zip(channels, _to_rgbe(red, green, blue)):
                channel.append(value)

        encoded.extend((2, 2, width >> 8, width & 255))
        for channel in channels:
            encoded.extend(_encode_radiance_channel(channel))
        row_count += 1

    if row_count != height:
        raise ValueError("Radiance row count does not match the image height.")
    return bytes(encoded)
