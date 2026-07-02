from pathlib import Path

from source.py.task.cjk import (
    CJKBuildConfig,
    CJKMasterSpec,
    CJKOutputConfig,
    CJKSourceConfig,
    CJKNamingConfig,
    CJKUnicodeConfig,
    DEFAULT_JP_RANGES,
    build_cjk_fonts,
)


def jp_config(jp_root: str = "./source/jp") -> CJKBuildConfig:
    """Return the built-in JP Resource Han preset."""
    jp_dir = Path(jp_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=jp_dir / "ResourceHanRoundedJP-VF.otf",
            masters=(
                CJKMasterSpec("min", {"wght": 200, "ROND": 100}),
                CJKMasterSpec("regular", {"wght": 400, "ROND": 100}),
                CJKMasterSpec("max", {"wght": 900, "ROND": 100}),
            ),
            outline_mode="cff2",
            drop_tables=(
                "BASE",
                "GDEF",
                "GPOS",
                "GSUB",
                "HVAR",
                "MVAR",
                "VORG",
                "VVAR",
                "vhea",
                "vmtx",
            ),
        ),
        output=CJKOutputConfig(
            dir=jp_dir,
            regular_variable="MapleMono-JP-VF.ttf",
            italic_variable="MapleMono-JP-Italic-VF.ttf",
            static_dir="static",
            static_hash="static.sha256",
            archive_name="jp-base-static.zip",
        ),
        naming=CJKNamingConfig(
            family_name="Maple Mono JP",
            postscript_prefix="MapleMonoJP",
            static_file_prefix="MapleMonoJP",
        ),
        unicode=CJKUnicodeConfig(ranges=DEFAULT_JP_RANGES, filter_encoding="cp932"),
        temp_dir=Path("source/jp/temp"),
        allow_incompatible_glyphs=True,
    )


def jp(jp_root: str, vf_only: bool = True) -> None:
    """Build JP fonts through the shared CJK pipeline."""
    build_cjk_fonts(jp_config(jp_root), vf_only)
