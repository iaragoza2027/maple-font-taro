# Google Fonts build and QA

The Google Fonts build uses the gftools recipe in `sources/config.yaml`. Its
canonical variable TTFs are written to `fonts/variable/`; the recipe also emits
the static, OTF, and webfont targets enabled by gftools defaults.

From the repository root, run:

```sh
uv run task.py googlefonts
uv run task.py googlefonts --qa
```

The task imports and calls `gftools.builder` directly; `uv run` only selects the
project environment for the outer task command.

Before every gftools build, the task regenerates the Designspace/UFO sources
from the exported `.glyphs` files. The `--qa` variant then removes the existing
`fonts/variable/` output, rebuilds it, and calls FontBakery directly with the
Google Fonts profile. Its markdown report is written to `fonts/report.md`.
FontBakery remains the authoritative Google Fonts profile, including Latin Core
coverage. Warnings must be reviewed rather than automatically suppressed.
