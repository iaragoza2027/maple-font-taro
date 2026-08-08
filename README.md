![Cover](./resources/header.png)

<p align="center">
  <a href="https://trendshift.io/repositories/13165" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13165" alt="subframe7536%2Fmaple-font | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
  <a href="https://hellogithub.com/repository/0601f355bd824d88b58f1af3066c486a" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=0601f355bd824d88b58f1af3066c486a&claim_uid=AO0yWRQ48ITGNqK" alt="Featured｜HelloGitHub" style="width: 250px; height: 54px;" width="250" height="54" /></a>
</p>
<p align="center">
  <img alt="GitHub Repo Stars" src="https://img.shields.io/github/stars/subframe7536/maple-font">
  <img alt="GitHub Repo Forks" src="https://img.shields.io/github/forks/subframe7536/maple-font">
  <img alt="X (formerly Twitter) Follow" src="https://img.shields.io/twitter/follow/subframe7536">
</p>
<p align="center">
  <img alt="GitHub Release" src="https://img.shields.io/github/v/release/subframe7536/maple-font">
  <img alt="GitHub Downloads (all assets, all releases)" src="https://img.shields.io/github/downloads/subframe7536/maple-font/total">
  <img alt="GitHub Repo License" src="https://img.shields.io/github/license/subframe7536/maple-font">
  <img alt="GitHub Repo Issues" src="https://img.shields.io/github/issues/subframe7536/maple-font">
</p>

<p align="center">
  <a href="#download-and-installation">Download</a> |
  <a href="https://font.subf.dev">Website</a> |
  English |
  <a href="./README_CN.md">简中</a> |
  <a href="./README_TC.md">繁中</a> |
  <a href="./README_JP.md">日本語</a> |
  <a href="./README_KR.md">한국어</a>
</p>

> [!WARNING]
> V8 is still under development and has not been officially released. If you need a stable version, please use the [`v7` branch](https://github.com/subframe7536/maple-font/tree/v7).

# Maple Mono

Maple Mono is an open-source monospace font designed to make coding more comfortable and efficient.

I created it to improve my own productivity, and hope it helps more people enjoy writing code.

## Why Maple Mono?

- ✨ **Variable font support** - Adjust the weight continuously, with carefully refined italic glyphs for flexible typography.
- ☁️ **Rounded shapes and visual refinement** - Rounded throughout, with redesigned `@ $ % & Q ->`, refined italic connections (`f i j k l x y`), and multiple character-width modes.
- 🪄 **Enhanced smart ligatures** - Extensive smart ligatures, character variants, OpenType stylistic sets, and built-in status-label ligatures make code easier to read and more expressive.
- 🔣 **Extended Unicode coverage** - Includes box-drawing characters, Braille, mathematical operators (U+2200–U+22FF), chess and card symbols, terminal status and progress symbols, and Claude Code loading indicators for scientific and development workflows.
- 🎨 **Nerd Font icon support** - Integrates [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) natively for clear, readable interfaces across development tools and terminals.
- 🔨 **Highly customizable builds** - Configure OpenType features, status-label ligatures, line height, character width, and weight mapping, or generate a custom font from source.

### Simplified Chinese, Traditional Chinese, Japanese, and Korean

Maple Mono supports CJK character sets. Compared with V7, V8 greatly expands and improves its CJK coverage for Simplified Chinese, Traditional Chinese, Japanese, and Korean. CJK glyphs use a 2:1 width ratio with Latin characters to keep multilingual text and Markdown tables aligned; as a trade-off, the default CJK spacing is wider than in many other CJK fonts. See [this issue](https://github.com/subframe7536/maple-font/issues/211) for details.

| Locale | Coverage                                                                | CJK font source                                                                                     | Build output |
| ------ | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------ |
| CN     | Simplified Chinese, with common Traditional Chinese and Japanese ranges | [WenYuan Rounded SC](https://github.com/takushun-wu/WenYuanFonts)                                   | `CN`         |
| TC     | Traditional Chinese                                                     | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc)                            | `TC`         |
| JP     | Japanese                                                                | [Resource Han Rounded JP](https://github.com/CyanoHao/Resource-Han-Rounded)                         | `JP`         |
| KR     | Korean                                                                  | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc), filtered to Korean ranges | `KR`         |

CJK builds are disabled by default. Use the CJK build configuration to select one or more locales, static or variable output, and optional compact spacing.

<!--
|Go|od| t|yp|og|ra|ph|y |re|ad|s |ea|si|ly|
|优|美|的|字|体|让|阅|读|变|得|更|加|轻|松|
|優|美|的|字|體|讓|閱|讀|變|得|更|加|輕|鬆|
|美|し|い|書|体|は|も|っ|と|読|み|や|す|い|
|아|름|다|운|글|꼴|은|더|읽|기|가|편|해|요|
|1!|2@|3#|4$|5%|6^|7&|8*|9(|0)|_+|{}|[]|;:|
-->

![2-1.png](./resources/2-1.png)

## Preview

![showcase.png](./resources/showcase.png)

- Generated with [CodeImg](https://github.com/subframe7536/vscode-codeimg)
- Theme: [Maple](https://github.com/subframe7536/vscode-theme-maple)
- Configuration: 16px font size, 1.8 line height, default letter spacing

## Getting Started

### Download and Installation

Download the font archives from [Releases](https://github.com/subframe7536/maple-font/releases/latest).

You can also install Maple Mono through Scoop, Homebrew, AUR/Paru, NixPkgs, and other package managers. See the [installation guide](./docs/install.md) for details.

### Usage and Feature Configuration

See the [usage guide](./docs/usage.md) for usage and configuration instructions.

#### Naming and Font Selection

Maple Mono provides multiple font formats and character-set ranges in its releases based on user feedback. Choose the font file that fits your use case; see [font selection](./docs/choose.md) for details.

### CDN

### Maple Mono

- [fontsource](https://fontsource.org/fonts/maple-mono)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/443/)

### Maple Mono CN

- [The Chinese Web Fonts Plan](https://chinese-font.netlify.app/zh-cn/fonts/maple-mono-cn/MapleMono-CN-Regular)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/442/)

## Highlights

You can preview all highlights on the [showcase page#todo]().

### Custom Builds

Maple Mono provides highly customizable builds. Modify [`config.json`](./config.json) or add command-line arguments to generate the font you need; see [custom builds](./docs/build.md) for details.

### Narrow Glyphs

V8 provides three character-width modes. Change the `"width"` field in [`config.json`](./config.json), or pass `--width <mode>` on the command line.

Available modes:

- default: 600
- narrow: 550
- slim: 500

[Preview#todo]()

### OpenType Feature Switches

OpenType features control built-in font variants and ligatures, and are supported by most modern operating systems, browsers, terminals, and editors. Enable or disable them to control ligatures and character styles.

Maple Mono provides many fine-grained OpenType features. To reduce configuration effort, builds support three handling modes ([why](https://github.com/subframe7536/maple-font/issues/233#issuecomment-2410170270)):

1. `enable`: Force these features on without setting `cvXX` / `ssXX` / `zero` in the font feature configuration, similar to default ligatures.
2. `disable`: Remove these features from `cvXX` / `ssXX` / `zero`, so they remain inactive even if enabled manually.
3. `ignore`: Keep the default behavior unchanged.

### Normal Preset

Maple Mono's default glyph design is distinctive and personalized, which may not suit every taste or use case. The `--normal` build preset provides glyphs similar to `JetBrains Mono` (`0` has a slash in the middle instead of a dot).

[Preview#todo]()

#### Custom OpenType Features, Such as Status-Label Ligatures

Most fonts do not support custom OpenType features, while Maple Mono supports defining them programmatically.

By default, the Python modules in [`scripts/feature/`](./scripts/feature) generate the OpenType feature code loaded during the build. Modify those modules to adjust behavior or customize labels. To edit `.fea` source files directly, pass `--apply-fea-file` to `build.py`; the build script will load [`source/features/{regular,italic}{_cn,}.fea`](./source/features).

### Infinite Arrow Ligatures

Inspired by Fira Code and Cascadia Code, Maple Mono has supported infinite arrow ligatures since v7.3. Because of rendering issues, arrow ligatures may be misaligned in hinted fonts, so Hinted versions have disabled this feature by default since v7.4.

Set `"infinite_arrow": true` in `config.json`, or pass `--infinite-arrow` on the command line to force-enable it. Discuss issues in [#508](https://github.com/subframe7536/maple-font/issues/508).

[Preview#todo]()

### Custom Line Height

Maple Mono's default line height is `1`. Change the `"line_height"` field in [`config.json`](./config.json), or pass `--line-height <value>` on the command line. The final line height is calculated as `(ascender - descender) * line_height`.

### Custom Unicode Mapping

If Maple Mono lacks a Unicode code point, the corresponding character may not render. Customize the mapping through the `"codepoint_alias"` field in [`config.json`](./config.json).

For example, map existing characters to other Unicode code points:

```json
{
  "codepoint_alias": {
    "U+E000": "U+E001",
    "U+E002": "U+E003"
  }
}
```

### Custom Weight Mapping

Change the weight of static fonts through the `"weight_mapping"` field in `config.json`.

For example, make the regular weight slightly thinner by lowering `"weight_mapping.regular"` from 400 to 350:

```json
{
  "weight_mapping": {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "regular": 350,
    "semibold": 500,
    "medium": 600,
    "bold": 700,
    "extrabold": 800
  }
}
```

### Custom Nerd Font Configuration

Maple Mono includes Nerd Font icons and follows its naming rules. By default, each icon occupies one Latin-character width.

- To make icons occupy two Latin-character widths (Nerd Font Mono), set `"nerd_font.mono": true` in `config.json`, or add `--nf-mono` to the build arguments.
- To use variable-width icons (Nerd Font Propo), set `"nerd_font.propo": true` in `config.json`, or add `--nf-propo` to the build arguments.

To customize `font-patcher` arguments, install `fontforge` (and possibly `python3-fontforge`). You may also need to change `"nerd_font.extra_args"` in [config.json](./config.json).

[Preview#todo]()

#### Argument Parsing Rules

Default arguments: `-l --careful --outputdir dir`

- When `"nerd_font.propo"` is `true`, add `--variable-width-glyphs`.
- When `"nerd_font.mono"` is `true`, add `--mono`.

## CJK Version

CJK fonts are not generated by default. Enable the CJK build configuration to download the required base glyphs from the [GitHub Release](https://github.com/subframe7536/maple-font/releases/tag/cjk-base).

### Narrow CJK Spacing

If only the CJK characters have **too much** spacing while Latin characters look correct, use the `cjk.narrow` build option or the `--cjk-narrow` command-line argument. This prevents the font from being recognized as strictly monospace.

See [#249](https://github.com/subframe7536/maple-font/issues/249#issuecomment-2871260476) for a preview and discussion.

- To change Latin character width as well, use the [`--width` option](#narrow-glyphs).

### GitHub Mirror

The build script automatically downloads required resources from GitHub. If a download fails, set `github_mirror` in [config.json](./config.json) or set `$GITHUB` as an environment variable. The target URL format is `https://<github_mirror>/<user>/<repo>/releases/download/<tag>/<file>`; you can also download the target `.zip` file and place it next to `build.py`.

#### Centered Full-Width Punctuation

Maple Mono supports the `cpct` feature to center full-width punctuation, which is common in Traditional Chinese; you can also enable `cv99` to force this behavior. See [#150](https://github.com/subframe7536/maple-font/issues/150) for details.

## Credits

- [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono)
- [Fira Code](https://github.com/tonsky/FiraCode)
- [Cascadia Code](https://github.com/microsoft/cascadia-code)
- [Roboto Mono](https://github.com/googlefonts/RobotoMono)
- [Victor Mono](https://github.com/rubjo/victor-mono)
- [Commit Mono](https://github.com/eigilnikolajsen/commit-mono)
- [Code Sample](https://github.com/TheRenegadeCoder/sample-programs-website)
- [Nerd Font](https://github.com/ryanoasis/nerd-fonts)
- [Font Freeze](https://github.com/MuTsunTsai/fontfreeze/)
- [Font Viewer](https://tophix.com/font-tools/font-viewer)
- [Monolisa](https://www.monolisa.dev/)
- [Recursive](https://www.recursive.design/)

## Sponsorship

If this font is helpful to you, please consider sponsoring me through [Afdian](https://afdian.com/a/subframe7536).

## Star History

<a href="https://www.star-history.com/#subframe7536/maple-font&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&legend=top-left" />
 </picture>
</a>

## License

SIL Open Font License 1.1
