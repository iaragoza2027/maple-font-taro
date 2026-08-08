![封面图](./resources/header.png)

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
  <a href="#下载">下载</a> |
  <a href="https://font.subf.dev">网站</a> |
  <a href="./README.md">English</a> |
  中文 |
  <a href="./README_JA.md">日本語</a>
</p>

# Maple Mono

Maple Mono 是一款开源等宽字体，专注于优化您的编码体验。

我制作它是为了提升自己的工作效率，希望它也能对其他人有所帮助。

您可以[在这里](https://github.com/subframe7536/maple-font/tree/v7)查看 V7 版本。

## 为什么选择 Maple Mono？

- ✨ **可变字体支持** - 支持连续字重调节，并优化细粒度斜体字形表现，提供更灵活的排版控制能力。
- ☁️ **圆角与视觉优化** - 全面圆角化处理，重绘 `@ $ % & Q ->` 等关键符号，优化斜体连笔（`f i j k l x y`），并提供多种宽度模式。
- 💪 **编程连字增强** - 强化编程连字支持，新增状态标签类连字、丰富字符变体与 OpenType Stylistic Sets，提升代码可读性与表达效率。
- 🔣 **Unicode 扩展覆盖** - 制表符、盲文、数学运算符（U+2200–U+22FF）、国际象棋与扑克牌符号、终端状态/进度符号、Claude Code 状态加载符号等完整符号集，增强科学与开发场景支持。
- 🎨 **Nerd Font 图标支持** - 原生集成 [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts)，无缝兼容各类开发工具与终端环境，显著增强界面信息表达与可读性。
- 🔨 **高度可定制构建** - 支持强制开启 OpenType 特性、自定义标签连字、自定义行高、宽度、字重映射等配置，并可从源码生成专属字体，满足个性化构建需求。

### **简体中文、繁体中文、日文与韩文**

Maple Mono 支持 CJK 字符集，相比于 V7，V8 版本的 CJK 字符集进行了大幅度的扩充和优化，支持简体中文、繁体中文、日文和韩文。同时，为了在多语言显示、Markdown 表格等场景做到整齐划一、美观舒适，本字体的 CJK 字符可以与英文字符 2:1 完美对齐；作为取舍，默认的 CJK 字符的间距相比其他流行的中文字体更大，详见[这个议题](https://github.com/subframe7536/maple-font/issues/211) 。

| 地区 | 覆盖范围                           | CJK 字库来源                                                                             | 构建输出 |
| ---- | ---------------------------------- | ---------------------------------------------------------------------------------------- | -------- |
| CN   | 简体中文，并覆盖常用繁体与日文字符 | [WenYuan Rounded SC](https://github.com/takushun-wu/WenYuanFonts)                        | `CN`     |
| TC   | 繁体中文                           | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc)                 | `TC`     |
| JP   | 日文                               | [Resource Han Rounded JP](https://github.com/CyanoHao/Resource-Han-Rounded)              | `JP`     |
| KR   | 韩文                               | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc)，按韩文区域筛选 | `KR`     |

CJK 构建默认关闭。可通过 CJK 构建配置选择地区、静态/可变输出以及是否启用紧凑宽度模式。

<!--
|Go|od| t|yp|og|ra|ph|y |re|ad|s |ea|si|ly|
|优|美|的|字|体|让|阅|读|变|得|更|加|轻|松|
|優|美|的|字|體|讓|閱|讀|變|得|更|加|輕|鬆|
|美|し|い|書|体|は|も|っ|と|読|み|や|す|い|
|아|름|다|운|글|꼴|은|더|읽|기|가|편|해|요|
|1!|2@|3#|4$|5%|6^|7&|8*|9(|0)|=+|{}|[]|;:|
-->

## 预览

![showcase.png](./resources/showcase.png)

- 生成：[CodeImg](https://github.com/subframe7536/vscode-codeimg)
- 主题：[Maple](https://github.com/subframe7536/vscode-theme-maple)
- 配置：字体大小 16px，行高 1.8，默认字母间距

## 开始使用

### 下载与安装

您可以从 [Releases](https://github.com/subframe7536/maple-font/releases/latest) 下载所有字体压缩包。

您也可以从 Scoop、Homebrew、AUR/Paru、NixPkgs 等包管理器安装 Maple Mono，详情见 [安装指南](./docs/install.md)。

### 使用与特性配置

请参阅 [使用指南](./docs/usage.md)

#### 命名说明与字体选择

不同于绝大部分字体，Maple Mono 根据用户反馈，在发行版中提供了多种字体格式和不同的字符集范围，您可以根据自己的需求选择合适的字体文件，详情见 [字体选择](./docs/choose.md)

### CDN

### Maple Mono

- [fontsource](https://fontsource.org/fonts/maple-mono)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/443/)

### Maple Mono CN

- [The Chinese Web Fonts Plan (中文网字计划)](https://chinese-font.netlify.app/zh-cn/fonts/maple-mono-cn/MapleMono-CN-Regular)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/442/)


## 亮点介绍

您可以在 [介绍页面#todo]() 预览所有亮点。

### 自定义构建

Maple Mono 提供了高度可定制的构建方式，您可以通过修改 [`config.json`](./config.json) 文件或在命令行中添加参数来生成符合您需求的字体文件，详情见 [自定义构建](./docs/build.md)。

### 窄字符

在 v8 版本中，Maple Mono 提供了三种不同的字符宽度选项，
您可以通过修改 [`config.json`](./config.json) 的 `"width"` 字段或在命令行中添加参数 `--width <mode>` 来选择不同的宽度模式。

有 3 个选项：

- default: 600
- narrow: 550
- slim: 500

[预览#todo]()

### OpenType 特性开关

“OpenType 特性”是一种可以控制字体的内置变体和连字的机制，被绝大多数现代化的操作系统、浏览器、终端、编辑器所支持。您可以通过开启或者关闭 OpenType 特性来控制一些连字的开关或者字符样式的变化。

Maple Mono 拥有大量的、细粒度的 OpenType 特性，为了减少使用时的配置时间，在构建时针对特性的开关提供了三种选项（[为什么](https://github.com/subframe7536/maple-font/issues/233#issuecomment-2410170270)）：

1. `enable`: 强制启用这些特性，而无需在字体特性配置中设置 `cvXX` / `ssXX` / `zero`，就像默认连字一样
2. `disable`: 删除 `cvXX` / `ssXX` / `zero` 中的特性，即使您手动启用它，也不在生效
3. `ignore`: 什么也不做

### Normal 预设

Maple Mono 的默认字形设计偏向于独特和个性化，这可能不适合所有用户的审美或使用场景。为了满足更多用户的需求，Maple Mono 提供了一个名为 `--normal` 的构建预设，可以提供类似 `JetBrains Mono`（除了 `0` 的中间是斜线而不是点）的字形。

以下是 `--normal` 参数启用的特性：
<!-- NORMAL -->

```
cv01, cv02, cv33, cv34, cv35, cv36, cv61, cv62, ss05, ss06, ss07, ss08
```

<!-- NORMAL -->

[预览#todo]()

#### 自定义 OpenType 特性（如添加标签连字内容）

绝大多数的字体都不支持自定义 OpenType 特性，Maple Mono 是少数提供了以编程的方式自定义 OpenType 特性功能的字体。

默认情况下，[`scripts/feature/`](./scripts/feature) 中的 Python 模块会生成 OpenType 特性字符串并在构建时加载。您可以在此处修改功能或自定义标签。如果你想通过修改 OpenType 特性源文件（.fea）实现，运行 `build.py` 时添加 `--apply-fea-file` 参数，会读取 [`source/features/{regular,italic}{_cn,}.fea`](./source/features) 的特性文件并加载。

### 无限箭头连字

受 Fira Code 和 Cascadia Code 的启发，从 v7.3 开始，Maple Mono 支持了无限箭头连字特性。由于某种未知的渲染原因，在使用 Hinted 字体时连字会错位，因此在 v7.4 的 Hinted 版本中默认将其移除。

您可以在 `config.json` 中设置 `"infinite_arrow": true`，或在命令行标志中添加 `--infinite-arrow` 强制开启或者关闭。如果有问题，请在 [#508](https://github.com/subframe7536/maple-font/issues/508) 内讨论

[预览#todo]()

### 自定义行高

Maple Mono 的默认行高为 `1`，您可以通过修改 [`config.json`](./config.json) 中的 `"line_height"` 字段或在命令行中添加参数 `--line-height <value>` 来修改行高，最终行高的计算公式为 `(ascender - descender) * line_height`。

### 自定义 Unicode 映射

Maple Mono 可能会缺少某些 Unicode 码点，导致某些字符无法显示。您可以通过修改 [`config.json`](./config.json) 中的 `"codepoint_alias"` 项来自定义 Unicode 映射。

例如，如果您想将某个字符映射到另一个 Unicode 码点：

```json
{
  "codepoint_alias": {
    "U+E000": "U+E001",
    "U+E002": "U+E003"
  }
}
```

### 自定义字重映射

您可以通过 `config.json` 中的 `"weight_mapping"` 项修改静态字体粗细。

例如，如果您想让常规字重稍微细一些，只需将 `"weight_mapping.regular"` 的数值降低（在此示例中从 400 降到 350）：

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

### 自定义 Nerd-Font

Maple Mono 内置了 Nerd-Font 图标支持，并遵守了其命名规则。默认情况下，图标的宽度是一个拉丁字符宽度。

- 如果您想获得两个拉丁字符宽度的图标（Nerd Font Mono），请在 `config.json` 中设置 `"nerd_font.mono": true` 或在构建脚本参数中添加 `--nf-mono` 标志。
- 如果您想获得可变宽度的图标（Nerd Font Propo），请在 `config.json` 中设置 `"nerd_font.propo": true` 或在构建脚本参数中添加 `--nf-propo` 标志。

对于自定义的 `font-patcher` 参数，需要 `font-forge`（也可能需要 `python3-fontforge`）。您可能还需要在 [config.json](./config.json) 中更改 `"nerd_font.extra_args"`。

[预览#todo]()

#### 参数解析规则

默认参数： `-l --careful --outputdir dir`

- 如果 `"nerd_font.propo"` 为 `true`，则添加 `--variable-width-glyphs`
- 如果 `"nerd_font.mono"` 为 `true`，则添加 `--mono`

## CJK 版本（中文）

默认情况下不会生成中文字体，运行 `python build.py` 时添加 `--cjk cn` 参数，中文基字将从 [GitHub Release](https://github.com/subframe7536/maple-font/releases/tag/cjk-base) 下载。

### 缩小中文字体的间距

如果您觉得只有中文字符的间距**过大**，而英文字符的间距正常，您可以通过构建选项 `cjk.narrow` 或 命令行参数 `--cjk-narrow` 缩小中文字符间距，但是这将让字体无法被识别为等宽字体。

您可以在 [#249](https://github.com/subframe7536/maple-font/issues/249#issuecomment-2871260476) 中查看效果或者讨论。

- 如果您也想改变拉丁字母的宽度，请使用 [`--width` 参数](#窄字符)

### GitHub 镜像

构建脚本将自动从 GitHub 下载所需的资源。如果您在下载时遇到问题，请在 [config.json](./config.json) 中设置 `github_mirror` 或将 `$GITHUB` 设置为您的环境变量。（目标 URL 为 `https://<github_mirror>/<user>/<repo>/releases/download/<tag>/<file>`），或者直接下载目标 `.zip` 文件并将其放在与 `build.py` 相同的目录中。

#### 繁体中文标点支持

通过开启 `cv99`，所有的中文标点符号都会居中，详情见 [#150](https://github.com/subframe7536/maple-font/issues/150)

## 我个人在用的其他中文字体资源

见 [cn-resource](https://github.com/subframe7536/maple-font/tree/other-resources/cn-resource) 和 [cn-base](https://github.com/subframe7536/maple-font/releases/tag/cn-base)

## 鸣谢

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

## 赞助

如果这个字体对您有所帮助，可以通过 [爱发电](https://afdian.com/a/subframe7536) 赞助我

## 点星

<a href="https://www.star-history.com/#subframe7536/maple-font&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=subframe7536/maple-font&type=date&legend=top-left" />
 </picture>
</a>

## 许可

SIL Open Font License 1.1
