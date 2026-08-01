# Texture Generation

Reusable Unreal Editor Python tools for deterministic texture generation and import.

The plugin is content-only. It requires no project C++ module and no rebuild when
a generator changes.

## Install

Add it as an Unreal project submodule:

```powershell
git submodule add https://github.com/MC-Oruc/TextureGeneration.git Plugins/TextureGeneration
```

For an existing checkout:

```powershell
git submodule update --init --recursive
```

Enable Unreal's Python Editor Script Plugin. The plugin's `Content/Python`
directory is discovered automatically, so no per-developer Python path is
required.

## Use

Run from Unreal's Python console:

```python
import texture_generation; texture_generation.run("wet_water_surface", "/Game/Generated/Textures")
```

Available generators:

- `wet_water_surface`: looping BC5 water-surface normal atlas with balanced
  macro oscillation and lightweight traveling micro detail.
- `wet_ripple_impacts`: two BC7 atlases with puddle normal in RG and wet-film
  normal in BA.
- `wet_surface_fields`: one BC7 packed field texture with two puddle-noise
  channels in RG and sparse glint placement data in BA.
- `wet_city_reflection`: bundled equirectangular panorama converted into a
  seam-safe Radiance HDR cubemap source with controlled emissive range and
  softly balanced horizontal city-light energy. The default source lives at
  `SourceArt/Environment/WetSurface/WetCityReflection_Source.tga`.
- `wet_neutral_surface_defaults`: canonical 4x4 solid neutral BaseColor,
  tangent Normal, and ORM defaults for shared wet-surface materials.

Or generate source files without importing:

```python
import texture_generation; texture_generation.generate_only("wet_water_surface")
```

Generated source images are written under the project's
`Saved/TextureGeneration` directory. Unreal assets are written to the supplied
content path.

## Architecture

- `main.py` dispatches a named Python module and owns the shared workflow.
- `common/` owns validation, source-image writing, and Unreal import/save logic.
- `generators/` owns texture-specific math, packing, names, and import settings.
- A generator returns one or more `TextureOutput` values. There is no recipe DSL.
- `TextureOutput` supports raw RGBA8/TGA or generator-owned encoded source data
  such as Radiance HDR.

Adding a texture type means adding one generator module. Shared import code does
not change.
