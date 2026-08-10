#!/usr/bin/env bash
# Build the two canonical, unhinted variable fonts submitted to Google Fonts.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
uv run build.py --format ttf --no-nf --no-hinted
install -d fonts/googlefonts
install -m 0644 'fonts/Variable/MapleMono[wght].ttf' 'fonts/googlefonts/MapleMono[wght].ttf'
install -m 0644 'fonts/Variable/MapleMono-Italic[wght].ttf' 'fonts/googlefonts/MapleMono-Italic[wght].ttf'
uv run python -m sources.qa_googlefonts fonts/googlefonts/*.ttf
