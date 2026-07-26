from __future__ import annotations

from pathlib import Path

from .models import TextureOutput


def _normalize_destination(destination_path: str) -> str:
    normalized = destination_path.rstrip("/")
    if not normalized.startswith("/Game/"):
        raise ValueError("Destination path must be under /Game.")
    return normalized


def _resolve_setting(unreal, value: object) -> object:
    if not isinstance(value, tuple) or len(value) != 2:
        return value
    enum_type = getattr(unreal, value[0])
    return getattr(enum_type, value[1])


def import_texture(
    output: TextureOutput,
    source_path: Path,
    destination_path: str,
) -> str:
    import unreal

    destination = _normalize_destination(destination_path)
    task = unreal.AssetImportTask()
    task.set_editor_property("automated", True)
    task.set_editor_property("destination_name", output.asset_name)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("filename", str(source_path.resolve()))
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", False)
    task.set_editor_property("save", False)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = list(task.get_editor_property("imported_object_paths"))
    if not imported_paths:
        raise RuntimeError(f"Unreal did not import {source_path}.")

    asset_path = imported_paths[0]
    texture = unreal.EditorAssetLibrary.load_asset(asset_path)
    if texture is None:
        raise RuntimeError(f"Could not load imported texture: {asset_path}")

    texture.modify()
    for property_name, value in output.texture_settings.items():
        texture.set_editor_property(property_name, _resolve_setting(unreal, value))

    if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
        raise RuntimeError(f"Could not save imported texture: {asset_path}")
    return asset_path
