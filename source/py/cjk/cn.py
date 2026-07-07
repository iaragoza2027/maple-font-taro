from source.py.cjk.presets import build_preset, build_preset_config


def cn_config(cn_root: str = "./source/cjk"):
    """Return the built-in CN preset."""
    return build_preset_config("cn", cn_root)


def cn(cn_root: str = "./source/cjk", vf_only: bool = False) -> None:
    """Build CN fonts through the shared CJK pipeline."""
    build_preset("cn", vf_only=vf_only, root=cn_root)
