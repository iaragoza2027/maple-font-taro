from scripts.cjk.presets import build_preset, build_preset_config


def kr_config(kr_root: str = "./source/cjk"):
    """Return the built-in KR preset."""
    return build_preset_config("kr", kr_root)


def kr(kr_root: str = "./source/cjk", vf_only: bool = True) -> None:
    """Build KR fonts through the shared CJK pipeline."""
    build_preset("kr", vf_only=vf_only, root=kr_root)
