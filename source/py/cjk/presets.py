from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from source.py.cjk.builder import build_cjk_fonts
from source.py.cjk.config import (
    CJKBuildConfig,
    CJKOutputConfig,
    CJKSourceConfig,
    CJKNamingConfig,
    CJKTransformConfig,
    CJKUnicodeConfig,
    DEFAULT_CJK_RANGES,
    DEFAULT_JP_RANGES,
    DEFAULT_KR_RANGES,
    DEFAULT_TC_RANGES,
)


CJKPresetId = Literal["cn", "jp", "tc", "kr"]


@dataclass(frozen=True)
class CJKPresetSpec:
    preset_id: CJKPresetId
    label: str
    root_dir: Path
    build_config: Callable[[str], CJKBuildConfig]
    family_suffix: str
    meta_languages: str
    code_page_range1: int
    weight_mapping_hint: dict[int, int] | None = None


def cn_config(cn_root: str = "./source/cn") -> CJKBuildConfig:
    cn_dir = Path(cn_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=cn_dir / "WenYuanRoundedSCVF.otf",
            masters={
                100: {"ital": 0, "wght": 220},
                400: {"ital": 0, "wght": 470},
                800: {"ital": 0, "wght": 900},
            },
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
        transform=CJKTransformConfig(
            x_scale=1.02,
            y_scale=1.05,
            x_shift=100,
            y_shift=-25,
        ),
        unicode=CJKUnicodeConfig(ranges=DEFAULT_CJK_RANGES),
        temp_dir=Path("source/cn/temp"),
    )


def jp_config(jp_root: str = "./source/jp") -> CJKBuildConfig:
    jp_dir = Path(jp_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=jp_dir / "ResourceHanRoundedJP-VF.otf",
            masters={
                100: {"wght": 200, "ROND": 100},
                400: {"wght": 400, "ROND": 100},
                800: {"wght": 900, "ROND": 100},
            },
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


def tc_config(tc_root: str = "./source/tc") -> CJKBuildConfig:
    tc_dir = Path(tc_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=tc_dir / "ChironGoRoundTCVF.otf",
            masters={
                100: {"wght": 250},
                400: {"wght": 620},
                800: {"wght": 900},
            },
            outline_mode="cff2",
            drop_tables=("BASE", "VVAR", "vhea", "vmtx"),
        ),
        output=CJKOutputConfig(
            dir=tc_dir,
            regular_variable="MapleMono-TC-VF.ttf",
            italic_variable="MapleMono-TC-Italic-VF.ttf",
            static_dir="static",
            static_hash="static.sha256",
            archive_name="tc-base-static.zip",
        ),
        naming=CJKNamingConfig(
            family_name="Maple Mono TC",
            postscript_prefix="MapleMonoTC",
            static_file_prefix="MapleMonoTC",
        ),
        unicode=CJKUnicodeConfig(ranges=DEFAULT_TC_RANGES),
        temp_dir=Path("source/tc/temp"),
        allow_incompatible_glyphs=True,
    )


def kr_config(kr_root: str = "./source/kr") -> CJKBuildConfig:
    kr_dir = Path(kr_root)
    return CJKBuildConfig(
        source=CJKSourceConfig(
            path=kr_dir / "ChironGoRoundTCVF.otf",
            masters={
                100: {"wght": 250},
                400: {"wght": 620},
                800: {"wght": 900},
            },
            outline_mode="cff2",
            drop_tables=("BASE", "VVAR", "vhea", "vmtx"),
        ),
        output=CJKOutputConfig(
            dir=kr_dir,
            regular_variable="MapleMono-KR-VF.ttf",
            italic_variable="MapleMono-KR-Italic-VF.ttf",
            static_dir="static",
            static_hash="static.sha256",
            archive_name="kr-base-static.zip",
        ),
        naming=CJKNamingConfig(
            family_name="Maple Mono KR",
            postscript_prefix="MapleMonoKR",
            static_file_prefix="MapleMonoKR",
        ),
        unicode=CJKUnicodeConfig(ranges=DEFAULT_KR_RANGES),
        temp_dir=Path("source/kr/temp"),
        allow_incompatible_glyphs=True,
    )


_PRESETS: dict[CJKPresetId, CJKPresetSpec] = {
    "cn": CJKPresetSpec(
        "cn",
        "Simplified Chinese",
        Path("./source/cn"),
        cn_config,
        "CN",
        "Latn, Hans, Hant, Jpan",
        1 << 0 | 1 << 17 | 1 << 18 | 1 << 20,
    ),
    "jp": CJKPresetSpec(
        "jp",
        "Japanese",
        Path("./source/jp"),
        jp_config,
        "JP",
        "Latn, Jpan",
        1 << 0 | 1 << 17,
    ),
    "tc": CJKPresetSpec(
        "tc",
        "Traditional Chinese",
        Path("./source/tc"),
        tc_config,
        "TC",
        "Latn, Hant",
        1 << 0 | 1 << 20,
        {100: 250, 400: 620, 800: 900},
    ),
    "kr": CJKPresetSpec(
        "kr",
        "Korean",
        Path("./source/kr"),
        kr_config,
        "KR",
        "Latn, Hang",
        1 << 0 | 1 << 19,
        {100: 250, 400: 620, 800: 900},
    ),
}


def list_presets() -> tuple[CJKPresetId, ...]:
    return tuple(_PRESETS.keys())


def get_preset(preset_id: CJKPresetId) -> CJKPresetSpec:
    return _PRESETS[preset_id]


def build_preset_config(preset_id: CJKPresetId, root: str | None = None) -> CJKBuildConfig:
    preset = get_preset(preset_id)
    return preset.build_config(root or str(preset.root_dir))


def build_preset(preset_id: CJKPresetId, vf_only: bool = False, root: str | None = None) -> None:
    build_cjk_fonts(build_preset_config(preset_id, root), vf_only=vf_only)
