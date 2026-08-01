from __future__ import annotations

from ..common.models import GenerationContext, TextureOutput


def _solid_rgba8(texel: tuple[int, int, int, int], width: int = 4, height: int = 4) -> bytes:
    return bytes(texel) * (width * height)


def generate(context: GenerationContext) -> list[TextureOutput]:
    del context
    return [
        TextureOutput(
            asset_name="T_WetDefault_BaseColor",
            width=4,
            height=4,
            rgba8=_solid_rgba8((255, 255, 255, 255)),
            texture_settings={
                "srgb": True,
                "compression_settings": ("TextureCompressionSettings", "TC_DEFAULT"),
                "mip_gen_settings": ("TextureMipGenSettings", "TMGS_NO_MIPMAPS"),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_WORLD"),
                "address_x": ("TextureAddress", "TA_CLAMP"),
                "address_y": ("TextureAddress", "TA_CLAMP"),
                "filter": ("TextureFilter", "TF_BILINEAR"),
            },
        ),
        TextureOutput(
            asset_name="T_WetDefault_Normal",
            width=4,
            height=4,
            rgba8=_solid_rgba8((128, 128, 255, 255)),
            texture_settings={
                "srgb": False,
                "compression_settings": ("TextureCompressionSettings", "TC_NORMALMAP"),
                "compression_no_alpha": True,
                "mip_gen_settings": ("TextureMipGenSettings", "TMGS_NO_MIPMAPS"),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_WORLD_NORMAL_MAP"),
                "address_x": ("TextureAddress", "TA_CLAMP"),
                "address_y": ("TextureAddress", "TA_CLAMP"),
                "filter": ("TextureFilter", "TF_BILINEAR"),
            },
        ),
        TextureOutput(
            asset_name="T_WetDefault_ORM",
            width=4,
            height=4,
            rgba8=_solid_rgba8((255, 128, 0, 255)),
            texture_settings={
                "srgb": False,
                "compression_settings": ("TextureCompressionSettings", "TC_MASKS"),
                "compression_no_alpha": True,
                "mip_gen_settings": ("TextureMipGenSettings", "TMGS_NO_MIPMAPS"),
                "lod_group": ("TextureGroup", "TEXTUREGROUP_WORLD_SPECULAR"),
                "address_x": ("TextureAddress", "TA_CLAMP"),
                "address_y": ("TextureAddress", "TA_CLAMP"),
                "filter": ("TextureFilter", "TF_BILINEAR"),
            },
        ),
    ]
