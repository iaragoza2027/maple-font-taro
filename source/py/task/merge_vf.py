from pathlib import Path
from source.py.task._utils_vf import merge_vf


def merge_variable_fonts(output_dir: str = "./fonts/Variable-CN"):
    """Merge Variable fonts with CN extension fonts."""
    base_dir = Path("fonts/Variable")
    cn_dir = Path("source/cn")
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    pairs = [
        (
            "MapleMono[wght].ttf",
            "MapleMono-CN-Extension-VF.ttf",
            "MapleMonoCN[wght].ttf",
        ),
        (
            "MapleMono-Italic[wght].ttf",
            "MapleMono-CN-Extension-Italic-VF.ttf",
            "MapleMonoCN-Italic[wght].ttf",
        ),
    ]

    for base_name, cn_name, output_name in pairs:
        base_path = base_dir / base_name
        cn_path = cn_dir / cn_name
        output_path = out / output_name

        if not base_path.exists():
            print(f"⚠️  Base font not found: {base_path}")
            continue
        if not cn_path.exists():
            print(f"⚠️  CN extension not found: {cn_path}")
            continue

        print(f"\n🔨 Merging {base_name} + {cn_name}")
        merged, added_glyphs, added_codepoints = merge_vf(base_path, cn_path)
        print(f"  Added glyphs: {len(added_glyphs)}")
        print(f"  Added codepoints: {added_codepoints}")

        merged.save(output_path)
        merged.close()
        print(f"✅ Saved: {output_path}")

    print(f"\n✅ Variable font merge complete: {output_dir}")
