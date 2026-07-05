from source.py.cjk.presets import build_preset, build_preset_config


def kr_config(kr_root: str = "./source/kr"):
    """Return the built-in KR preset skeleton based on todo.md mapping."""
    return build_preset_config("kr", kr_root)


def kr(kr_root: str, vf_only: bool = True) -> None:
    """Build KR fonts through the shared CJK pipeline."""
    build_preset("kr", vf_only=vf_only, root=kr_root)
