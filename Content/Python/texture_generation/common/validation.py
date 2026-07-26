from __future__ import annotations

import re
from collections.abc import Sequence

from .models import TextureOutput

_ASSET_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_outputs(outputs: Sequence[TextureOutput]) -> None:
    if not outputs:
        raise ValueError("A generator must produce at least one texture.")

    names: set[str] = set()
    for output in outputs:
        if not _ASSET_NAME.fullmatch(output.asset_name):
            raise ValueError(f"Invalid Unreal asset name: {output.asset_name}")
        if output.asset_name in names:
            raise ValueError(f"Duplicate output asset name: {output.asset_name}")
        if output.width <= 0 or output.height <= 0:
            raise ValueError(f"{output.asset_name} has invalid dimensions.")
        expected_bytes = output.width * output.height * 4
        if len(output.rgba8) != expected_bytes:
            raise ValueError(
                f"{output.asset_name} has {len(output.rgba8)} bytes; expected {expected_bytes}."
            )
        names.add(output.asset_name)
