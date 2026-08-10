# Google Fonts build and QA

The Google Fonts profile builds only the canonical Maple Mono Latin Regular and
Italic variable TTFs. It deliberately disables Nerd Font injection, CJK merging,
hinting, OTF, and WOFF2 output without changing the normal release defaults.

From the repository root, run:

```sh
./sources/build.sh
uv run fontbakery check-googlefonts fonts/googlefonts/*.ttf
```

The first command writes `MapleMono[wght].ttf` and
`MapleMono-Italic[wght].ttf` to `fonts/googlefonts/` and checks embedding,
monospace, variable-axis, naming, licensing, and vertical-metric metadata.
FontBakery remains the authoritative Google Fonts profile, including Latin Core
coverage. Warnings must be reviewed rather than automatically suppressed.
