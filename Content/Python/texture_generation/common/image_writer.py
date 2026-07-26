from __future__ import annotations

import struct
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
