from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

from .common.image_writer import write_tga
from .common.models import GenerationContext, TextureOutput
from .common.validation import validate_outputs

_GENERATOR_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _load_generator(name: str):
    if not _GENERATOR_NAME.fullmatch(name):
        raise ValueError("Generator names may contain lowercase letters, numbers, and underscores.")
    return importlib.import_module(f"{__package__}.generators.{name}")


def _default_source_root(generator_name: str) -> Path:
    try:
        import unreal
    except ImportError:
        return Path.cwd() / "Saved" / "TextureGeneration" / generator_name

    project_saved = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()))
    return project_saved / "TextureGeneration" / generator_name


def generate_only(
    generator_name: str,
    source_root: str | Path | None = None,
    **generator_options: Any,
) -> list[tuple[TextureOutput, Path]]:
    root = Path(source_root) if source_root else _default_source_root(generator_name)
    context = GenerationContext(source_root=root)
    module = _load_generator(generator_name)
    outputs = list(module.generate(context, **generator_options))
    validate_outputs(outputs)

    written: list[tuple[TextureOutput, Path]] = []
    for output in outputs:
        source_path = root / f"{output.asset_name}.tga"
        write_tga(source_path, output.width, output.height, output.rgba8)
        written.append((output, source_path))
    return written


def run(
    generator_name: str,
    destination_path: str,
    source_root: str | Path | None = None,
    **generator_options: Any,
) -> list[str]:
    from .common.unreal_import import import_texture

    written = generate_only(generator_name, source_root, **generator_options)
    return [
        import_texture(output, source_path, destination_path)
        for output, source_path in written
    ]
