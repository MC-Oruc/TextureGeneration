from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class GenerationContext:
    source_root: Path


@dataclass(frozen=True)
class TextureOutput:
    asset_name: str
    width: int
    height: int
    rgba8: bytes | bytearray
    texture_settings: Mapping[str, object] = field(default_factory=dict)
