# Naming and Choosing Fonts

Maple Mono release packages are split by font features, character width, font format, and character set. The examples below use the default base name `MapleMono`; if you customize the base name, the other components follow the same rules.

## Quick Selection

| Use case                     | Recommended choice                    | Why                                                                                                    |
| ---------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| General coding               | `TTF` or `OTF`                        | TTF has the broadest compatibility; OTF or unhinted TTF can be preferable on high-resolution displays. |
| Low-resolution displays      | `TTF-AutoHint`                        | Autohinting improves small-size TrueType rasterization.                                                |
| Web pages                    | `WOFF2`                               | The compressed format is smaller and works well with CSS font loading.                                 |
| Terminal icons               | `NF`                                  | Includes Nerd Font icons; configure the terminal to use the corresponding NF font.                     |
| Icons and CJK together       | `NF-CN`, `NF-TC`, `NF-JP`, or `NF-KR` | Includes Nerd Font icons and the selected CJK locale.                                                  |
| Continuous weight adjustment | `Variable`                            | Use the `wght` axis to select a weight without installing multiple static files.                       |

## Filename Components

### Features and Character Widths

Filename components are combined in this order: base name, feature preset, width, and style. Feature and width suffixes are compact, so they are not separated by additional hyphens.

| Configuration                      | Suffix     | Example family name    | Description                                                                                                                  |
| ---------------------------------- | ---------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Default ligatures                  | None       | `Maple Mono`           | The default glyph design and ligature behavior.                                                                              |
| Ligatures disabled                 | `NL`       | `Maple Mono NL`        | Disables the default ligatures; for example, `MapleMonoNL-Regular.ttf`.                                                      |
| `--normal` preset                  | `Normal`   | `Maple Mono Normal`    | Uses glyph designs closer to common programming fonts; see the [`--normal` preset in README.md](../README.md#normal-preset). |
| `--normal` with ligatures disabled | `NormalNL` | `Maple Mono Normal NL` | Applies both `Normal` and `NL`.                                                                                              |
| Default width                      | None       | `Maple Mono`           | Latin glyph target width is 600.                                                                                             |
| Narrow width                       | `NR`       | `Maple Mono NR`        | The `narrow` mode, with a Latin glyph target width of 550.                                                                   |
| Slim width                         | `SL`       | `Maple Mono SL`        | The `slim` mode, with a Latin glyph target width of 500.                                                                     |

For example, `--normal --no-liga --width narrow` produces `MapleMonoNormalNLNR-Regular.ttf`. Width settings also apply to Variable, NF, and CJK outputs.

### Font Formats

| Format or marker | Example                       | Description                                                                                         |
| ---------------- | ----------------------------- | --------------------------------------------------------------------------------------------------- |
| `Variable`       | `MapleMono[wght].ttf`         | A variable font whose weight is controlled through the `wght` axis. Italic files include `-Italic`. |
| `TTF`            | `MapleMono-Regular.ttf`       | A static TrueType font with broad application compatibility.                                        |
| `OTF`            | `MapleMono-Regular.otf`       | A static OpenType font for desktop applications with OpenType support.                              |
| `WOFF2`          | `MapleMono-Regular.ttf.woff2` | A compressed WOFF2 font intended mainly for web pages.                                              |
| `NF`             | `MapleMono-NF-Regular.ttf`    | Includes Nerd Font icons; `NF` can also be combined with feature and width suffixes.                |

### CJK Character Sets

CJK outputs use a locale suffix. Regular CJK and NF-CJK fonts are written to `fonts/<LOCALE>/` and `fonts/NF-<LOCALE>/`; Variable outputs use the corresponding `Variable-<LOCALE>` and `Variable-NF-<LOCALE>` directories.

| Locale | Coverage                                                                | Regular CJK example        | NF-CJK example                |
| ------ | ----------------------------------------------------------------------- | -------------------------- | ----------------------------- |
| `CN`   | Simplified Chinese, with common Traditional Chinese and Japanese ranges | `MapleMono-CN-Regular.ttf` | `MapleMono-NF-CN-Regular.ttf` |
| `TC`   | Traditional Chinese                                                     | `MapleMono-TC-Regular.ttf` | `MapleMono-NF-TC-Regular.ttf` |
| `JP`   | Japanese                                                                | `MapleMono-JP-Regular.ttf` | `MapleMono-NF-JP-Regular.ttf` |
| `KR`   | Korean                                                                  | `MapleMono-KR-Regular.ttf` | `MapleMono-NF-KR-Regular.ttf` |

Locales can be combined with feature and width settings. For example, `--cjk jp --nf --width slim` produces the static file `MapleMonoSL-NF-JP-Regular.ttf`. CJK builds are disabled by default; see the [build guide](build.md) for configuration details.

## Hinted and Unhinted Fonts

Hinted fonts include TrueType rasterization instructions and are suited to low-resolution displays and small font sizes. Choose `TTF-AutoHint`, or use the default hinted `NF` and `NF-CJK` outputs.

Unhinted fonts omit those instructions and are suited to high-resolution displays such as modern MacBooks. Choose `OTF`, regular `TTF`, or an `NF` / CJK release package whose name includes `-unhinted`; on low-resolution displays, unhinted fonts may look blurry, misaligned, or uneven in weight.

`-AutoHint` and `-unhinted` identify release packages or output directories; they are not OpenType features. `-AutoHint` is used only for automatically hinted TTF output, and both suffixes are retained for compatibility with existing installation workflows and naming conventions.
