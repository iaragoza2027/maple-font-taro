from scripts.cjk.presets import build_preset, build_preset_config


def tc_config(tc_root: str = "./source/cjk"):
    """Return the built-in TC preset."""
    return build_preset_config("tc", tc_root)


def tc(tc_root: str = "./source/cjk", vf_only: bool = True) -> None:
    """Build TC fonts through the shared CJK pipeline."""
    build_preset("tc", vf_only=vf_only, root=tc_root)
