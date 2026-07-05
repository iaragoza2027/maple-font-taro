from source.py.cjk.presets import build_preset, build_preset_config


def jp_config(jp_root: str = "./source/jp"):
    """Return the built-in JP preset."""
    return build_preset_config("jp", jp_root)


def jp(jp_root: str, vf_only: bool = True) -> None:
    """Build JP fonts through the shared CJK pipeline."""
    build_preset("jp", vf_only=vf_only, root=jp_root)
