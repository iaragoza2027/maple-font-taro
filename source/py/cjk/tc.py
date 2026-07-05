from source.py.cjk.presets import build_preset, build_preset_config


def tc_config(tc_root: str = "./source/tc"):
    """Return the built-in TC preset skeleton based on todo.md mapping."""
    return build_preset_config("tc", tc_root)


def tc(tc_root: str, vf_only: bool = True) -> None:
    """Build TC fonts through the shared CJK pipeline."""
    build_preset("tc", vf_only=vf_only, root=tc_root)
