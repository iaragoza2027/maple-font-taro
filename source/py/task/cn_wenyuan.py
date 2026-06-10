from functools import partial
from os import listdir, makedirs, path
from pathlib import Path
import shutil
import sys
from typing import Callable, Iterable

from source.py.utils import get_directory_hash, joinPaths, run

# Add cn directory to sys.path for build_variable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cn"))
from build_variable import (  # noqa: E402
    build_cn_extension,
    make_italic,
    DEFAULT_ITALIC_ANGLE,
)


def run_pool_process(fn: Callable, items: Iterable):
    from multiprocessing import Pool

    with Pool(processes=4) as pool:
        pool.map(fn, items)


def instantiate_wenyuan_var(
    f: str, base_dir: str, static_dir: str, italic_tmp_dir: str
):
    output_dir = italic_tmp_dir if "Italic" in f else static_dir
    run(
        f"ftcli converter var2static -out {output_dir} {joinPaths(base_dir, f)}",
        log=True,
    )


def flatten_italic_fonts(italic_tmp_dir: str, target_dir: str):
    for f in listdir(italic_tmp_dir):
        shutil.move(
            joinPaths(italic_tmp_dir, f),
            joinPaths(
                target_dir,
                f if "Italic" in f else f.replace(".ttf", "Italic.ttf"),
            ),
        )
    shutil.rmtree(italic_tmp_dir)


def optimize_wenyuan_base(f: str, base_dir: str):
    font_path = joinPaths(base_dir, f)
    print(f"✨ Optimize {font_path}")
    run(f"ftcli font del-table -t kern -t GPOS {font_path}", log=True)


def update_dir_hash(dir: str):
    run(f"ftcli name del-mac-names -r {dir}")
    with open(f"{dir}.sha256", "w") as f:
        f.write(get_directory_hash(dir))
        f.flush()
    print(f"#️⃣ Update {dir}.sha256")


def rename_wenyuan_files(static_dir: str):
    """Rename generated files to match MapleMonoCN-*.ttf pattern."""
    weight_map = {
        "100": "Thin",
        "210": "ExtraLight",
        "320": "Light",
        "400": "Regular",
        "490": "Medium",
        "570": "SemiBold",
        "680": "Bold",
        "800": "ExtraBold",
    }

    for f in listdir(static_dir):
        if not f.endswith(".ttf"):
            continue

        # Extract weight from MapleMonoCNFeatures-wght_XXX_0[Italic].ttf
        for weight_num, weight_name in weight_map.items():
            if f"wght_{weight_num}_0" in f:
                is_italic = "Italic" in f
                new_name = (
                    f"MapleMonoCN-{weight_name}{'Italic' if is_italic else ''}.ttf"
                ).replace("RegularItalic", "Italic")  # Handle RegularItalic case
                old_path = joinPaths(static_dir, f)
                new_path = joinPaths(static_dir, new_name)
                shutil.move(old_path, new_path)
                break


def cn_wenyuan(cn_root: str, rebuild: bool = True):

    print("🔨 Building CN WenYuan extension fonts...")

    # Build variable fonts (cn-extension only, no merge)
    feature_font_path = Path("source/MapleMono-CN-feature-VF.ttf")
    wenyuan_source = Path("source/cn/WenYuanRoundedSCVF.ttf")
    regular_base = Path("fonts/Variable/MapleMono[wght].ttf")
    italic_base = Path("fonts/Variable/MapleMono-Italic[wght].ttf")

    # Build cn-extension variable fonts
    cn_extension = build_cn_extension(
        feature_font_path=feature_font_path,
        wenyuan_source=wenyuan_source,
        regular_base_path=regular_base,
        italic_base_path=italic_base,
        dry_run=False,
    )
    italic_cn_extension = make_italic(cn_extension, DEFAULT_ITALIC_ANGLE)

    # Save variable fonts temporarily
    var_output = joinPaths(cn_root, "MapleMono-CN-Extension-VF.ttf")
    var_italic_output = joinPaths(cn_root, "MapleMono-CN-Extension-Italic-VF.ttf")

    print(f"💾 Save variable fonts to {cn_root}")
    cn_extension.save(var_output)
    italic_cn_extension.save(var_italic_output)
    cn_extension.close()
    italic_cn_extension.close()

    # Instantiate to static
    static_dir = joinPaths(cn_root, "static-wenyuan")
    italic_tmp_dir = joinPaths(static_dir, "italic")
    makedirs(static_dir, exist_ok=True)

    var_font_names = [
        "MapleMono-CN-Extension-VF.ttf",
        "MapleMono-CN-Extension-Italic-VF.ttf",
    ]

    print("📐 Instantiating static fonts...")
    run_pool_process(
        partial(
            instantiate_wenyuan_var,
            base_dir=cn_root,
            static_dir=static_dir,
            italic_tmp_dir=italic_tmp_dir,
        ),
        var_font_names,
    )

    # Flatten italic fonts
    flatten_italic_fonts(italic_tmp_dir, static_dir)

    # Optimize static fonts
    run_pool_process(
        partial(optimize_wenyuan_base, base_dir=static_dir), listdir(static_dir)
    )

    # Rename files to match MapleMonoCN-*.ttf pattern
    rename_wenyuan_files(static_dir)

    # Update directory hash
    update_dir_hash(static_dir)

    print("✅ CN WenYuan rebuild complete.")
