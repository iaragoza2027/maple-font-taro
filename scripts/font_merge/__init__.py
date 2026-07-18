import json
from os import mkdir, remove, path, makedirs
from pathlib import Path
import uuid
import shutil

from scripts.common.files import join_path
from scripts.font_merge.models import FontSource, MergeConfig, PreparedSource
from scripts.font_merge.utils import instantiate, merge_fonts, polish

CONFIG_FILE = "config_merge.json"


def is_ascii_path(path_str: str) -> bool:
    """Check if path contains only ASCII characters."""
    try:
        path_str.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def copy_to_tmp_with_ascii_name(src_path: str, tmp_dir: str) -> str:
    """Copy font to tmp directory with ASCII-only filename."""
    temp_filename = f"{uuid.uuid4().hex}.ttf"
    temp_path = join_path(tmp_dir, temp_filename)
    shutil.copy(src_path, temp_path)
    return temp_path


def generate_example_config() -> str:
    """Generate example config content."""
    example = {
        "family_name": "MyCustomFont",
        "output_dir": "./fonts",
        "line_height": 1,
        "instances": {
            "Regular": ["path/to/base/font.ttf"],
            "Bold": [
                "path/to/base/font.ttf",
                {
                    "path": "path/to/bold/override.ttf",
                    "unicode_range": ["U+0030-0039", "U+0041-005A"],
                    "width_scale": 1.06,
                },
            ],
            "Italic": [
                {"path": "path/to/variable/font.ttf", "axes": {"slnt": -12}},
                {
                    "path": "path/to/italic/override.ttf",
                    "enable": True,
                    "unicode_range": ["U+0020-007E"],
                },
            ],
        },
    }
    return json.dumps(example, indent=2)


def load_config() -> MergeConfig:
    """Load the config file."""
    if not path.exists(CONFIG_FILE):
        example_content = generate_example_config()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(example_content)
        print(f"Config file '{CONFIG_FILE}' not found.")
        print(f"Created example config file: {CONFIG_FILE}")
        print("\nExample config content:")
        print(example_content)
        print("\nPlease edit the config file with your actual font paths and settings.")
        exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return MergeConfig.parse(json.load(f))


def prepare_font_source(
    source: FontSource, output_dir: str, label: str, tmp_dir: str
) -> PreparedSource:
    """
    Prepare a font source for merging.

    Returns:
        {
            "path": str,           # Resolved font path (may be in tmp)
            "is_temp": bool,       # Whether the file is temporary
            "unicode_range": list,  # Parsed unicode ranges (for overrides only)
            "width_scale": float,   # Width scale factor (for overrides only)
        }
    """
    font_path = str(source.path)
    if not path.exists(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")

    is_temp = False
    if source.axes:
        print(f"  Instantiating {label} from {font_path} with axes {source.axes}...")
        temp_filename = f"inst_{label}_{uuid.uuid4().hex[:8]}.ttf"
        temp_path = join_path(tmp_dir, temp_filename)
        instantiate(font_path, temp_path, source.axes)
        print(f"  Instantiated: {temp_path}")
        font_path = temp_path
        is_temp = True
    elif not is_ascii_path(font_path):
        print(f"  Copying non-ASCII path font to tmp: {font_path}")
        font_path = copy_to_tmp_with_ascii_name(font_path, output_dir)
        is_temp = True

    return PreparedSource(
        path=Path(font_path),
        is_temp=is_temp,
        unicode_ranges=source.unicode_ranges,
        width_scale=source.width_scale,
    )


def main(cleanup: bool = False):
    print("Font merge script (Multi-Font Support)")

    # Load and validate config
    config = load_config()
    family_name = config.family_name
    output_dir = str(config.output_dir)
    line_height_config = config.line_height
    instances = config.instances

    # Create directories
    if not path.exists(output_dir):
        mkdir(output_dir)
        print(f"Created output directory: {output_dir}")

    tmp_dir = join_path(output_dir, "tmp")
    makedirs(tmp_dir, exist_ok=True)

    # Track temporary files and generated files
    temp_files_to_clean = []
    generated_files: list[str] = []

    for style_name, font_sources in instances.items():
        print(f"\n{'=' * 60}")
        print(f"Processing: {family_name} — {style_name}")
        print(f"{'=' * 60}")

        if (
            not font_sources
            or not isinstance(font_sources, list)
            or len(font_sources) == 0
        ):
            print(
                f"Warning: No font sources defined for style '{style_name}'. Skipping."
            )
            continue

        try:
            # Prepare base font (first source)
            print("\n1. Preparing base font...")
            base_config = prepare_font_source(
                font_sources[0], output_dir, f"{style_name}_base", tmp_dir
            )
            if base_config.is_temp:
                temp_files_to_clean.append(str(base_config.path))
            print(f"  Base font: {base_config.path}")

            # Prepare override fonts (remaining sources)
            print("\n2. Preparing override fonts...")
            overrides = []
            for idx, source in enumerate(font_sources[1:], start=1):
                # Check enable flag for override configs
                if not source.enable:
                    print(f"  Override {idx} is disabled. Skipping.")
                    continue

                override_config = prepare_font_source(
                    source, output_dir, f"{style_name}_override_{idx}", tmp_dir
                )

                print(f"  Override {idx}: {override_config.path}")
                if override_config.is_temp:
                    temp_files_to_clean.append(str(override_config.path))

                overrides.append(override_config)

            if not overrides:
                print("No enabled overrides. Using base font only.")

            # Merge fonts
            print("\n3. Merging fonts...")
            merged_path = merge_fonts(
                output_dir=output_dir,
                base_font_path=str(base_config.path),
                overrides=overrides,
                tmp_dir=tmp_dir,
            )
            print(f"  Merged temporary file: {merged_path}")
            temp_files_to_clean.append(merged_path)

            # Polish
            print("\n4. Finalizing (naming and metrics)...")
            final_path = polish(
                font_path=merged_path,
                output_dir=output_dir,
                family_name=family_name,
                style_name=style_name,
                line_height_config=line_height_config,
            )
            print(f"  Completed: {final_path}")
            generated_files.append(final_path)

        except Exception as e:
            print(f"\n❌ Error processing style '{style_name}': {e}")
            continue

    # Cleanup temporary files (only on success for each style)
    print("\n" + "=" * 60)
    if cleanup:
        print("Cleaning up temporary files...")
        shutil.rmtree(tmp_dir)
        for temp_file in temp_files_to_clean:
            if path.exists(temp_file):
                try:
                    remove(temp_file)
                except Exception as e:
                    print(f"Failed to remove {temp_file}: {e}")

        print("\nAll tasks finished.")

    if generated_files:
        print("\nGenerated files:")
        for p in generated_files:
            print(f"  - {p}")
    else:
        print("\nNo output files were generated.")
