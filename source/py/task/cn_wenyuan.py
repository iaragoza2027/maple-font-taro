from pathlib import Path

from source.py.task.cjk import (
    CJKBuildConfig,
    CJKMasterSpec,
    CJKOutputConfig,
    CJKSourceConfig,
    CJKNamingConfig,
    CJKUnicodeConfig,
    DEFAULT_CJK_RANGES,
    build_cjk_fonts,
)


def cn_wenyuan_config(cn_root: str = "./source/cn") -> CJKBuildConfig:
    """Return the built-in CN WenYuan preset."""
    cn_dir = Path(cn_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=cn_dir / "WenYuanRoundedSCVF.ttf",
            masters=(
                CJKMasterSpec("min", {"ital": 0, "wght": 220}),
                CJKMasterSpec("regular", {"ital": 0, "wght": 470}),
                CJKMasterSpec("max", {"ital": 0, "wght": 900}),
            ),
            outline_mode="glyf",
            drop_tables=("BASE", "VVAR", "vhea", "vmtx"),
        ),
        output=CJKOutputConfig(
            dir=cn_dir,
            regular_variable="MapleMono-CN-VF.ttf",
            italic_variable="MapleMono-CN-Italic-VF.ttf",
            static_dir="static-wenyuan",
            static_hash="static-wenyuan.sha256",
            archive_name="cn-base-static-wenyuan.zip",
        ),
        naming=CJKNamingConfig(
            family_name="Maple Mono CN",
            postscript_prefix="MapleMonoCN",
            static_file_prefix="MapleMonoCN",
        ),
        unicode=CJKUnicodeConfig(ranges=DEFAULT_CJK_RANGES),
        temp_dir=Path("source/cn/temp"),
    )


def cn_wenyuan(cn_root: str, vf_only: bool = False) -> None:
    """Build CN WenYuan fonts through the shared CJK pipeline."""
    build_cjk_fonts(cn_wenyuan_config(cn_root), vf_only)
