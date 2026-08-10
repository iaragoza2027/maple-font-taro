"""Check metadata required by the Maple Mono Google Fonts build."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scripts.font_ops.fonttools import TTFont

logger = logging.getLogger(__name__)

REQUIRED_TABLES = frozenset({"STAT", "fvar", "name", "OS/2", "post"})
REQUIRED_NAME_IDS = (0, 1, 2, 3, 4, 5, 6, 13, 14)


def validate_font(path: Path) -> None:
    with TTFont(path) as font:
        missing_tables = REQUIRED_TABLES.difference(font.keys())
        assert not missing_tables, f"{path}: missing tables: {sorted(missing_tables)}"
        os2 = font["OS/2"]
        assert os2.fsType == 0, f"{path}: OS/2.fsType must be 0"
        assert font["post"].isFixedPitch == 1, f"{path}: post.isFixedPitch must be 1"
        assert os2.panose.bProportion == 9, (
            f"{path}: PANOSE proportion must be monospaced (9)"
        )
        axes = {axis.axisTag: axis for axis in font["fvar"].axes}
        assert "wght" in axes, f"{path}: missing wght axis"
        weight = axes["wght"]
        assert weight.minValue <= 400 <= weight.maxValue, f"{path}: wght excludes 400"
        names = font["name"]
        missing_names = [
            name_id for name_id in REQUIRED_NAME_IDS if not names.getName(name_id, 3, 1)
        ]
        assert not missing_names, (
            f"{path}: missing Windows English names {missing_names}"
        )
        assert os2.sTypoAscender > 0 and os2.sTypoDescender < 0
        assert os2.usWinAscent > 0 and os2.usWinDescent > 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fonts", nargs="+", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for font in args.fonts:
        validate_font(font)
        logger.info("Google Fonts metadata OK: %s", font)


if __name__ == "__main__":
    main()
