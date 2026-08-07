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

## 特性

<!--todo)) 更新-->

- ✨ 可变 - 无限的字体粗细，以及手工微调的斜体字形。
- ☁️ 丝滑 - **圆角**，独特的 `@ $ % & Q ->` 字形，以及手写风格的斜体 `f i j k l x y`。
- 💪 实用 - 大量的智能连字，详见 [`features/`](./source/features/README.md)。
- 🎨 图标 - 提供 [Nerd-Font](https://github.com/ryanoasis/nerd-fonts) 嵌入的版本，添加图标支持。
- 🔨 定制 - 自由开关或者构建 OpenType 字体特性，打造您专属的字体。

### 简体中文、繁体中文、日文与韩文

Maple Mono 支持 CJK 字符集，相比于 V7，V8 版本的 CJK 字符集进行了大幅度的扩充，支持简体中文、繁体中文、日文和韩文。同时，为了在多语言显示、Markdown 表格等场景做到整齐划一、美观舒适，本字体的 CJK 字符可以与英文字符 2:1 完美对齐；作为取舍，CJK 字符的间距相比其他流行的中文字体更大，详见[这个议题](https://github.com/subframe7536/maple-font/issues/211)。

![2-1.png](./resources/2-1.png)

## 屏幕截图

![showcase.png](./resources/showcase.png)

- 生成：[CodeImg](https://github.com/subframe7536/vscode-codeimg)
- 主题：[Maple](https://github.com/subframe7536/vscode-theme-maple)
- 配置：字体大小 16px，行高 1.8，默认字母间距

## 下载

您可以从 [Releases](https://github.com/subframe7536/maple-font/releases) 下载所有字体压缩包。

您也可以从 Scoop、Homebrew、AUR/Paru、NixPkgs 等包管理器安装 Maple Mono。

<!--todo)) 单独的文档-->

## CDN

### Maple Mono

- [fontsource](https://fontsource.org/fonts/maple-mono)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/443/)

### Maple Mono CN

- [The Chinese Web Fonts Plan (中文网字计划)](https://chinese-font.netlify.app/zh-cn/fonts/maple-mono-cn/MapleMono-CN-Regular)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/442/)

## 使用方法 & 特性配置

请参阅 [文档](./source/features/README_CN.md) 或者在 [特性测试页面](https://font.subf.dev/zh-cn/playground) 尝试。

## 命名说明

<!--todo)) 单独的文档（v8新增了宽度，需要添加）-->

### 字体特性

- **Ligature**: 带有连字的默认版本 (`Maple Mono`)
- **No-Ligature**: 没有连字的默认版本 (`Maple Mono NL`)
- **Normal-Ligature**: 带有连字的 [`--normal` 预设](#预设) (`Maple Mono Normal`)
- **Normal-No-Ligature**: 没有连字的 [`--normal` 预设](#预设) (`Maple Mono Normal NL`)

### 字体格式和字符集

- **Variable**: 最小版本，通过字体的可变轴改变字体粗细
- **TTF**: 最小版本，ttf 格式 [推荐！]
- **OTF**: 最小版本，otf 格式
- **WOFF2**: 最小版本，woff2 格式，多用于网页加载
- **NF**: 嵌入 Nerd-Font 的版本，为终端添加图标 (带有 `-NF` 后缀)
- **CN**: 中文版本，嵌入中文和日文字形 (带有 `-CN` 后缀)
- **NF-CN**: 完整版本，嵌入图标、中文和日文字形 (带有 `-NF-CN` 后缀)

### 字体微调

- **Hinted 字体** 用于低分辨率屏幕，以获得更好的渲染效果。根据我个人的经验，如果您的屏幕分辨率低于或等于 1080P，建议使用 "hinted 字体"。使用 "unhinted 字体" 会导致文本错位或粗细不均。
  - 在这种情况下，您可以选择 `MapleMono-TTF-AutoHint` / `MapleMono-NF` / `MapleMono-NF-CN` 等。
- **Unhinted 字体** 用于高分辨率屏幕（例如 MacBook）。使用 "hinted 字体" 会使您的文本模糊或看起来很奇怪。
  - 在这种情况下，您可以选择 `MapleMono-OTF` / `MapleMono-TTF` / `MapleMono-NF-unhinted` / `MapleMono-NF-CN-unhinted` 等。
- 为什么存在 `-AutoHint` 和 `-unhinted` 后缀？
  - 为了向后兼容，我保留了原始命名方案。`-AutoHint` 仅用于 `TTF` 格式。

## 自定义构建

<!--todo)) 单独的文档-->

[`config.json`](./config.json) 文件用于配置构建过程。查看 [schema](./source/schema.json) 或 [文档](./source/features/README.md) 了解更多详情。

还有一些 [命令行选项](#构建脚本用法) 用于自定义构建过程。命令行选项的优先级高于 `config.json` 中的选项。

### 构建方法

#### 1. 浏览器中构建

进入 [特性测试页面](https://font.subf.dev/zh-cn/playground)，点击左下角的“自定义构建”按钮

- 目前只支持固定 OpenType 特性

#### 2. 使用 Github Actions

您可以使用 [Github Actions](https://github.com/subframe7536/maple-font/actions/workflows/custom.yml) 来构建字体。

1. Fork 仓库
2. (可选) 更改 `config.json` 中的内容
3. 转到 Actions 选项卡
4. 点击左侧的 `Custom Build` 菜单项
5. 点击 `Run workflow` 按钮并设置选项
6. 等待构建完成
7. 从 Releases 下载字体压缩包

#### 3. 使用 Docker

```shell
git clone https://github.com/subframe7536/maple-font --depth 1 -b variable
docker build -t maple-font .
docker run -v "$(pwd)/fonts:/app/fonts" -e BUILD_ARGS="--normal" maple-font
```

#### 4. 本地构建

克隆仓库并在您的本地机器上运行。确保您已安装 `python3` 和 `pip`

```shell
git clone https://github.com/subframe7536/maple-font --depth 1 -b variable
pip install -r requirements.txt
python build.py
```

> [!TIP]
> 对于 `Ubuntu` 或 `Debian`，可能还需要 `python-is-python3`
>
> 如果您在安装依赖项时遇到问题，只需创建一个新的 GitHub Codespace 并在那里运行命令

## 特性

<!--todo)) 单独的文档-->

### 窄字符

你可以在 config.json 中设置 `"width": "narrow"` 或者在命令行添加 `--width slim` 来在构建时修改字形宽度。中文字符部分也会等比例修改。

有 3 个选项：

- default: 600
- narrow: 550
- slim: 500

预览：[#131](https://github.com/subframe7536/maple-font/issues/131#issuecomment-3678666194)

### 自定义 Nerd-Font

如果您想获得固定宽度的图标，请在 `config.json` 中设置 `"nerd_font.mono": true` 或在构建脚本参数中添加 `--nf-mono` 标志。

如果您想获得可变宽度的图标，请在 `config.json` 中设置 `"nerd_font.propo": true` 或在构建脚本参数中添加 `--nf-propo` 标志。

对于自定义的 `font-patcher` 参数，需要 `font-forge`（也可能需要 `python3-fontforge`）。

您可能还应该在 [config.json](./config.json) 中更改 `"nerd_font.extra_args"`。

默认参数： `-l --careful --outputdir dir`

- 如果 `"nerd_font.propo"` 为 `true`，则添加 `--variable-width-glyphs`
- 否则，如果 `"nerd_font.mono"` 为 `true`，则添加 `--mono`

### 预设

如果您想要获得固定宽度的 Nerd Font 图标，只需要在 `config.json` 中设置 `"nerd_font.mono": true` 或者在构建脚本中添加 `--nf-mono` 参数即可。

运行 `build.py` 时添加 `--normal` 参数，让字形不那么独特~~奇怪~~，就像 `JetBrains Mono` 一样（除了 `0` 的中间是斜线而不是点）。

如果您使用的是可变字体（不推荐），请启用 `calt` 特性以使所有特性正常工作。

启用的特性：
<!-- NORMAL -->

```
cv01, cv02, cv33, cv34, cv35, cv36, cv61, cv62, ss05, ss06, ss07, ss08
```

<!-- NORMAL -->

[在线预览](https://font.subf.dev/zh-cn/playground?normal)

### OpenType 特性强制开启

有三种选项（[为什么](https://github.com/subframe7536/maple-font/issues/233#issuecomment-2410170270)）：

1. `enable`: 强制启用这些特性，而无需在字体特性配置中设置 `cvXX` / `ssXX` / `zero`，就像默认连字一样
2. `disable`: 删除 `cvXX` / `ssXX` / `zero` 中的特性，即使您手动启用它，也不在生效
3. `ignore`: 什么也不做

#### 自定义 OpenType 特性

OpenType 特性可以控制字体的内置变体和连字。您可以通过修改 OpenType 特性来删除一些不需要的连字或特征，修改特征的触发规则或添加一些新规则。

默认情况下，[`source/py/feature/`](./source/py/feature) 中的 Python 模块会生成 OpenType 特性字符串并在构建时加载。您可以在此处修改功能或自定义标签。

如果你想通过修改 OpenType 特性文件实现，运行 `build.py` 时添加 `--apply-fea-file` 参数，会读取 [`source/features/{regular,italic}{_cn,}.fea`](./source/features) 的特性文件并加载。

### 无限箭头连字

受 Fira Code 的启发，从 v7.3 开始，该字体默认启用无限箭头连字。由于某种原因，在使用 Hinted 字体时连字会错位，因此在 v7.4 的 Hinted 版本中默认将其移除。

您可以在 `config.json` 中设置 `"infinite_arrow": true`，或在命令行标志中添加 `--infinite-arrow`。详情见 [#508](https://github.com/subframe7536/maple-font/issues/508)

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

## 中文版本

默认情况下不会生成中文字体，运行 `python build.py` 时添加 `--cjk cn` 参数，中文基字（约 111 MB）将从 GitHub 下载。

#### 缩小中文字体的间距

如果您觉得中文字符的间距**过大**，有一个构建选项 `cn.narrow` 或 命令行参数 `--cn-narrow` 可以缩小间距，但是这将让字体无法被识别为等宽字体。

您可以在 [#249](https://github.com/subframe7536/maple-font/issues/249#issuecomment-2871260476) 中查看效果。

如果您也想改变拉丁字母的宽度，请使用 [`--width` 参数](#窄字符)

#### GitHub 镜像

构建脚本将自动从 GitHub 下载所需的资源。如果您在下载时遇到问题，请在 [config.json](./config.json) 中设置 `github_mirror` 或将 `$GITHUB` 设置为您的环境变量。（目标 URL 为 `https://<github_mirror>/<user>/<repo>/releases/download/<tag>/<file>`），或者直接下载目标 `.zip` 文件并将其放在与 `build.py` 相同的目录中。

#### 繁體中文標點符號支援

<!--todo)) 繁体中文专属-->

通過開啟 `cv99`，所有的中文標點符號都會居中，詳情見 [#150](https://github.com/subframe7536/maple-font/issues/150)

## 我个人在用的其他中文字体资源

[cn-resource](https://github.com/subframe7536/maple-font/tree/other-resources/cn-resource)

## 鸣谢

- [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono)
- [Roboto Mono](https://github.com/googlefonts/RobotoMono)
- [Fira Code](https://github.com/tonsky/FiraCode)
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
