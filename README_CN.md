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
  <a href="./README_JP.md">日本語</a> |
  <a href="./README_TC.md">繁中</a> |
  <a href="./README_KR.md">한국어</a>
</p>

# Maple Mono

Maple Mono 是一款开源等宽字体，专注于优化您的编码体验。

我制作它是为了提升自己的工作效率，希望它也能对其他人有所帮助。

V8 是 Maple Mono 的下一个开发版本。它将原来的 CN CJK 构建扩展为 CN、TC、JP、KR 四个 locale，并增加更多 Unicode 覆盖；V8 发布前会合并到 `variable` 分支。当前稳定版本仍然是 V7.9。

> [!WARNING]
> V8 仍在开发中，尚未正式发布。GitHub 最新 Release、包管理器和 CDN 当前提供的都是 **V7.9**。下面的安装命令用于稳定版；如果要测试 V8，请使用源码构建。正式发布前，输出名称和构建选项可能变化。

## 特性

### 字体与连字

- 可变字重轴、细致调整的斜体字形，以及 default、narrow、slim 三种拉丁字宽。
- 智能编程连字包括 `[DEBUG]`、`[TODO]`、`[SUCCESS]` 等状态标签和无限箭头连字。
- 字符变体与 stylistic set 覆盖常见编码偏好，包括无尾 `u`、更长的 `|`，以及保加利亚/塞尔维亚西里尔字形（`cv12`、`cv45`、`cv67`、`ss12`、`ss13`）。完整说明见 [`source/features/README.md`](./source/features/README.md)。

### Unicode 与集成

- 覆盖 U+2200–U+22FF 数学符号、上下标、棋子/扑克牌符号以及终端进度和状态符号。
- 提供 [Nerd Font](https://github.com/ryanoasis/nerd-fonts) 图标版本，并支持冻结 OpenType 特性和自定义构建。

### CJK 扩展字体

V8 支持将 Maple Mono 与四个 locale 的 CJK 基础字体合并。每个 locale 都支持静态和可变输出；默认 CJK 字形使用中英文 2:1 宽度，适合多语言文本和 Markdown 表格。

| Locale | 覆盖范围 | CJK 来源 | 输出后缀 |
| --- | --- | --- | --- |
| CN | 简体中文，以及常用繁体中文和日文范围 | [WenYuan Rounded SC](https://github.com/takushun-wu/WenYuanFonts) | `CN` |
| TC | 繁体中文 | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc) | `TC` |
| JP | 日文 | [Resource Han Rounded JP](https://github.com/CyanoHao/Resource-Han-Rounded) | `JP` |
| KR | 韩文 | [Chiron Go Round TC](https://github.com/chiron-fonts/chiron-go-round-tc)，再按 KR 范围筛选 | `KR` |

默认不会构建 CJK 扩展字体。请参阅[下面的 CJK 构建说明](#cjk-扩展版本)选择 locale、静态或可变输出，以及可选的窄间距。

![2-1.png](./resources/2-1.png)

## 屏幕截图

![showcase.png](./resources/showcase.png)

- 生成：[CodeImg](https://github.com/subframe7536/vscode-codeimg)
- 主题：[Maple](https://github.com/subframe7536/vscode-theme-maple)
- 配置：字体大小 16px，行高 1.8，默认字母间距

## 下载

请选择适合编辑器或终端的稳定版 V7.9。您可以从 [GitHub Releases](https://github.com/subframe7536/maple-font/releases) 下载，也可以使用下面的包管理器。当前包管理器和 CDN 不会提供尚未发布的 V8 CJK 扩展版本。

| 需求 | 推荐包 |
| --- | --- |
| 日常编程 | Maple Mono TTF（低分辨率屏幕选 hinted，高分辨率屏幕选 unhinted） |
| 终端图标 | Maple Mono NF |
| 中日韩字形 | Maple Mono CN 或 Maple Mono NF CN（V7.9 稳定包） |
| 连续字重 | Maple Mono Variable；V8 CJK 可变版本需要按下方说明源码构建 |

### Scoop (Windows)

```sh
# Add bucket
scoop bucket add nerd-fonts
# Maple Mono (ttf 格式)
scoop install Maple-Mono
# Maple Mono NF
scoop install Maple-Mono-NF
# Maple Mono NF CN
scoop install Maple-Mono-NF-CN
```

<details>
  <summary>所有包 (点击展开)</summary>

  ```sh
  # 添加 bucket
  scoop bucket add nerd-fonts
  # Maple Mono (ttf 格式)
  scoop install Maple-Mono
  # Maple Mono (hinted ttf 格式)
  scoop install Maple-Mono-autohint
  # Maple Mono (otf 格式)
  scoop install Maple-Mono-otf
  # Maple Mono NF
  scoop install Maple-Mono-NF
  # Maple Mono NF CN
  scoop install Maple-Mono-NF-CN
  ```

</details>

### Homebrew (MacOS, Linux)

```sh
# Maple Mono
brew install --cask font-maple-mono
# Maple Mono NF
brew install --cask font-maple-mono-nf
# Maple Mono NF CN
brew install --cask font-maple-mono-nf-cn
```

<details>
  <summary>所有包 (点击展开)</summary>

  ```sh
  # Maple Mono
  brew install --cask font-maple-mono
  # Maple Mono NF
  brew install --cask font-maple-mono-nf
  # Maple Mono CN
  brew install --cask font-maple-mono-cn
  # Maple Mono NF CN
  brew install --cask font-maple-mono-nf-cn

  # Maple Mono Normal
  brew install --cask font-maple-mono-normal
  # Maple Mono Normal NF
  brew install --cask font-maple-mono-normal-nf
  # Maple Mono Normal CN
  brew install --cask font-maple-mono-normal-cn
  # Maple Mono Normal NF CN
  brew install --cask font-maple-mono-normal-nf-cn
  ```

</details>

### Arch Linux

ArchLinuxCN 仓库允许下载单个软件包的 zip 文件，而无需下载 pkgbase 中的所有软件包的 zip 文件，但 AUR 不允许。(如果您有好的解决方案，请联系 Cyberczy(czysheep@gmail.com))

#### ArchLinuxCN (推荐)

```sh
# Maple Mono (Ligature TTF unhinted)
paru -S ttf-maplemono
# Maple Mono NF (Ligature unhinted)
paru -S ttf-maplemono-nf-unhinted
# Maple Mono NF CN (Ligature unhinted)
paru -S ttf-maplemono-nf-cn-unhinted
```

<details>
  <summary>所有包 (点击展开)</summary>

  ```sh
  # Maple Mono (Ligature Variable)
  paru -S ttf-maplemono-variable
  # Maple Mono (Ligature TTF hinted)
  paru -S ttf-maplemono-autohint
  # Maple Mono (Ligature TTF unhinted)
  paru -S ttf-maplemono
  # Maple Mono (Ligature OTF)
  paru -S otf-maplemono
  # Maple Mono (Ligature WOFF2)
  paru -S woff2-maplemono
  # Maple Mono NF (Ligature hinted)
  paru -S ttf-maplemono-nf
  # Maple Mono NF (Ligature unhinted)
  paru -S ttf-maplemono-nf-unhinted
  # Maple Mono CN (Ligature hinted)
  paru -S ttf-maplemono-cn
  # Maple Mono CN (Ligature unhinted)
  paru -S ttf-maplemono-cn-unhinted
  # Maple Mono NF CN (Ligature hinted)
  paru -S ttf-maplemono-nf-cn
  # Maple Mono NF CN (Ligature unhinted)
  paru -S ttf-maplemono-nf-cn-unhinted

  # Maple Mono (No-Ligature Variable)
  paru -S ttf-maplemononl-variable
  # Maple Mono (No-Ligature TTF hinted)
  paru -S ttf-maplemononl-autohint
  # Maple Mono (No-Ligature TTF unhinted)
  paru -S ttf-maplemononl
  # Maple Mono (No-Ligature OTF)
  paru -S otf-maplemononl
  # Maple Mono (No-Ligature WOFF2)
  paru -S woff2-maplemononl
  # Maple Mono NF (No-Ligature hinted)
  paru -S ttf-maplemononl-nf
  # Maple Mono NF (No-Ligature unhinted)
  paru -S ttf-maplemononl-nf-unhinted
  # Maple Mono CN (No-Ligature hinted)
  paru -S ttf-maplemononl-cn
  # Maple Mono CN (No-Ligature unhinted)
  paru -S ttf-maplemononl-cn-unhinted
  # Maple Mono NF CN (No-Ligature hinted)
  paru -S ttf-maplemononl-nf-cn
  # Maple Mono NF CN (No-Ligature unhinted)
  paru -S ttf-maplemononl-nf-cn-unhinted

  # Maple Mono Normal (Ligature Variable)
  paru -S ttf-maplemononormal-variable
  # Maple Mono Normal (Ligature TTF hinted)
  paru -S ttf-maplemononormal-autohint
  # Maple Mono Normal (Ligature TTF unhinted)
  paru -S ttf-maplemononormal
  # Maple Mono Normal (Ligature OTF)
  paru -S otf-maplemononormal
  # Maple Mono Normal (Ligature WOFF2)
  paru -S woff2-maplemononormal
  # Maple Mono Normal NF (Ligature hinted)
  paru -S ttf-maplemononormal-nf
  # Maple Mono Normal NF (Ligature unhinted)
  paru -S ttf-maplemononormal-nf-unhinted
  # Maple Mono Normal CN (Ligature hinted)
  paru -S ttf-maplemononormal-cn
  # Maple Mono Normal CN (Ligature unhinted)
  paru -S ttf-maplemononormal-cn-unhinted
  # Maple Mono Normal NF CN (Ligature hinted)
  paru -S ttf-maplemononormal-nf-cn
  # Maple Mono Normal NF CN (Ligature unhinted)
  paru -S ttf-maplemononormal-nf-cn-unhinted

  # Maple Mono Normal (No-Ligature Variable)
  paru -S ttf-maplemononormalnl-variable
  # Maple Mono Normal (No-Ligature TTF hinted)
  paru -S ttf-maplemononormalnl-autohint
  # Maple Mono Normal (No-Ligature TTF unhinted)
  paru -S ttf-maplemononormalnl
  # Maple Mono Normal (No-Ligature OTF)
  paru -S otf-maplemononormalnl
  # Maple Mono Normal (No-Ligature WOFF2)
  paru -S woff2-maplemononormalnl
  # Maple Mono Normal NF (No-Ligature hinted)
  paru -S ttf-maplemononormalnl-nf
  # Maple Mono Normal NF (No-Ligature unhinted)
  paru -S ttf-maplemononormalnl-nf-unhinted
  # Maple Mono Normal CN (No-Ligature hinted)
  paru -S ttf-maplemononormalnl-cn
  # Maple Mono Normal CN (No-Ligature unhinted)
  paru -S ttf-maplemononormalnl-cn-unhinted
  # Maple Mono Normal NF CN (No-Ligature hinted)
  paru -S ttf-maplemononormalnl-nf-cn
  # Maple Mono Normal NF CN (No-Ligature unhinted)
  paru -S ttf-maplemononormalnl-nf-cn-unhinted
  ```

</details>

#### AUR (不推荐)

```sh
# Maple Mono (Ligature TTF unhinted)
paru -S maplemono-ttf
# Maple Mono NF (Ligature unhinted)
paru -S maplemono-nf-unhinted
# Maple Mono NF CN (Ligature unhinted)
paru -S maplemono-nf-cn-unhinted
```

<details>
  <summary>所有包 (点击展开)</summary>

  ```sh
  # Maple Mono (Ligature Variable)
  paru -S maplemono-variable
  # Maple Mono (Ligature TTF hinted)
  paru -S maplemono-ttf-autohint
  # Maple Mono (Ligature TTF unhinted)
  paru -S maplemono-ttf
  # Maple Mono (Ligature OTF)
  paru -S maplemono-otf
  # Maple Mono (Ligature WOFF2)
  paru -S maplemono-woff2
  # Maple Mono NF (Ligature hinted)
  paru -S maplemono-nf
  # Maple Mono NF (Ligature unhinted)
  paru -S maplemono-nf-unhinted
  # Maple Mono CN (Ligature hinted)
  paru -S maplemono-cn
  # Maple Mono CN (Ligature unhinted)
  paru -S maplemono-cn-unhinted
  # Maple Mono NF CN (Ligature hinted)
  paru -S maplemono-nf-cn
  # Maple Mono NF CN (Ligature unhinted)
  paru -S maplemono-nf-cn-unhinted

  # Maple Mono (No-Ligature Variable)
  paru -S maplemononl-variable
  # Maple Mono (No-Ligature TTF hinted)
  paru -S maplemononl-ttf-autohint
  # Maple Mono (No-Ligature TTF unhinted)
  paru -S maplemononl-ttf
  # Maple Mono (No-Ligature OTF)
  paru -S maplemononl-otf
  # Maple Mono (No-Ligature WOFF2)
  paru -S maplemononl-woff2
  # Maple Mono NF (No-Ligature hinted)
  paru -S maplemononl-nf
  # Maple Mono NF (No-Ligature unhinted)
  paru -S maplemononl-nf-unhinted
  # Maple Mono CN (No-Ligature hinted)
  paru -S maplemononl-cn
  # Maple Mono CN (No-Ligature unhinted)
  paru -S maplemononl-cn-unhinted
  # Maple Mono NF CN (No-Ligature hinted)
  paru -S maplemononl-nf-cn
  # Maple Mono NF CN (No-Ligature unhinted)
  paru -S maplemononl-nf-cn-unhinted

  # Maple Mono Normal (Ligature Variable)
  paru -S maplemononormal-variable
  # Maple Mono Normal (Ligature TTF hinted)
  paru -S maplemononormal-ttf-autohint
  # Maple Mono Normal (Ligature TTF unhinted)
  paru -S maplemononormal-ttf
  # Maple Mono Normal (Ligature OTF)
  paru -S maplemononormal-otf
  # Maple Mono Normal (Ligature WOFF2)
  paru -S maplemononormal-woff2
  # Maple Mono Normal NF (Ligature hinted)
  paru -S maplemononormal-nf
  # Maple Mono Normal NF (Ligature unhinted)
  paru -S maplemononormal-nf-unhinted
  # Maple Mono Normal CN (Ligature hinted)
  paru -S maplemononormal-cn
  # Maple Mono Normal CN (Ligature unhinted)
  paru -S maplemononormal-cn-unhinted
  # Maple Mono Normal NF CN (Ligature hinted)
  paru -S maplemononormal-nf-cn
  # Maple Mono Normal NF CN (Ligature unhinted)
  paru -S maplemononormal-nf-cn-unhinted

  # Maple Mono Normal (No-Ligature Variable)
  paru -S maplemononormalnl-variable
  # Maple Mono Normal (No-Ligature TTF hinted)
  paru -S maplemononormalnl-ttf-autohint
  # Maple Mono Normal (No-Ligature TTF unhinted)
  paru -S maplemononormalnl-ttf
  # Maple Mono Normal (No-Ligature OTF)
  paru -S maplemononormalnl-otf
  # Maple Mono Normal (No-Ligature WOFF2)
  paru -S maplemononormalnl-woff2
  # Maple Mono Normal NF (No-Ligature hinted)
  paru -S maplemononormalnl-nf
  # Maple Mono Normal NF (No-Ligature unhinted)
  paru -S maplemononormalnl-nf-unhinted
  # Maple Mono Normal CN (No-Ligature hinted)
  paru -S maplemononormalnl-cn
  # Maple Mono Normal CN (No-Ligature unhinted)
  paru -S maplemononormalnl-cn-unhinted
  # Maple Mono Normal NF CN (No-Ligature hinted)
  paru -S maplemononormalnl-nf-cn
  # Maple Mono Normal NF CN (No-Ligature unhinted)
  paru -S maplemononormalnl-nf-cn-unhinted
  ```

</details>

### Nixpkgs (NixOS, Linux, MacOS)

```nix
fonts.packages = with pkgs; [
  # Maple Mono (Ligature TTF unhinted)
  maple-mono.truetype
  # Maple Mono NF (Ligature unhinted)
  maple-mono.NF-unhinted
  # Maple Mono NF CN (Ligature unhinted)
  maple-mono.NF-CN-unhinted
];
```

<details>
  <summary>所有包 (点击展开)</summary>

  ```nix
  fonts.packages = with pkgs; [
    # Maple Mono (Ligature Variable)
    maple-mono.variable
    # Maple Mono (Ligature TTF hinted)
    maple-mono.truetype-autohint
    # Maple Mono (Ligature TTF unhinted)
    maple-mono.truetype
    # Maple Mono (Ligature OTF)
    maple-mono.opentype
    # Maple Mono (Ligature WOFF2)
    maple-mono.woff2
    # Maple Mono NF (Ligature hinted)
    maple-mono.NF
    # Maple Mono NF (Ligature unhinted)
    maple-mono.NF-unhinted
    # Maple Mono CN (Ligature hinted)
    maple-mono.CN
    # Maple Mono CN (Ligature unhinted)
    maple-mono.CN-unhinted
    # Maple Mono NF CN (Ligature hinted)
    maple-mono.NF-CN
    # Maple Mono NF CN (Ligature unhinted)
    maple-mono.NF-CN-unhinted

    # Maple Mono (No-Ligature Variable)
    maple-mono.NL-Variable
    # Maple Mono (No-Ligature TTF hinted)
    maple-mono.NL-TTF-AutoHint
    # Maple Mono (No-Ligature TTF unhinted)
    maple-mono.NL-TTF
    # Maple Mono (No-Ligature OTF)
    maple-mono.NL-OTF
    # Maple Mono (No-Ligature WOFF2)
    maple-mono.NL-Woff2
    # Maple Mono NF (No-Ligature hinted)
    maple-mono.NL-NF
    # Maple Mono NF (No-Ligature unhinted)
    maple-mono.NL-NF-unhinted
    # Maple Mono CN (No-Ligature hinted)
    maple-mono.NL-CN
    # Maple Mono CN (No-Ligature unhinted)
    maple-mono.NL-CN-unhinted
    # Maple Mono NF CN (No-Ligature hinted)
    maple-mono.NL-NF-CN
    # Maple Mono NF CN (No-Ligature unhinted)
    maple-mono.NL-NF-CN-unhinted

    # Maple Mono Normal (Ligature Variable)
    maple-mono.Normal-Variable
    # Maple Mono Normal (Ligature TTF hinted)
    maple-mono.Normal-TTF-AutoHint
    # Maple Mono Normal (Ligature TTF unhinted)
    maple-mono.Normal-TTF
    # Maple Mono Normal (Ligature OTF)
    maple-mono.Normal-OTF
    # Maple Mono Normal (Ligature WOFF2)
    maple-mono.Normal-Woff2
    # Maple Mono Normal NF (Ligature hinted)
    maple-mono.Normal-NF
    # Maple Mono Normal NF (Ligature unhinted)
    maple-mono.Normal-NF-unhinted
    # Maple Mono Normal CN (Ligature hinted)
    maple-mono.Normal-CN
    # Maple Mono Normal CN (Ligature unhinted)
    maple-mono.Normal-CN-unhinted
    # Maple Mono Normal NF CN (Ligature hinted)
    maple-mono.Normal-NF-CN
    # Maple Mono Normal NF CN (Ligature unhinted)
    maple-mono.Normal-NF-CN-unhinted

    # Maple Mono Normal (No-Ligature Variable)
    maple-mono.NormalNL-Variable
    # Maple Mono Normal (No-Ligature TTF hinted)
    maple-mono.NormalNL-TTF-AutoHint
    # Maple Mono Normal (No-Ligature TTF unhinted)
    maple-mono.NormalNL-TTF
    # Maple Mono Normal (No-Ligature OTF)
    maple-mono.NormalNL-OTF
    # Maple Mono Normal (No-Ligature WOFF2)
    maple-mono.NormalNL-Woff2
    # Maple Mono Normal NF (No-Ligature hinted)
    maple-mono.NormalNL-NF
    # Maple Mono Normal NF (No-Ligature unhinted)
    maple-mono.NormalNL-NF-unhinted
    # Maple Mono Normal CN (No-Ligature hinted)
    maple-mono.NormalNL-CN
    # Maple Mono Normal CN (No-Ligature unhinted)
    maple-mono.NormalNL-CN-unhinted
    # Maple Mono Normal NF CN (No-Ligature hinted)
    maple-mono.NormalNL-NF-CN
    # Maple Mono Normal NF CN (No-Ligature unhinted)
    maple-mono.NormalNL-NF-CN-unhinted
  ];
  ```

</details>

## CDN

下面的 CDN 链接提供稳定版 **V7.9**，不提供尚未发布的 V8 CJK 扩展版本。

### Maple Mono

- [fontsource](https://fontsource.org/fonts/maple-mono)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/443/)

### Maple Mono CN (V7.9)

- [The Chinese Web Fonts Plan (中文网字计划)](https://chinese-font.netlify.app/zh-cn/fonts/maple-mono-cn/MapleMono-CN-Regular)
- [ZeoSeven Fonts](https://fonts.zeoseven.com/items/442/)

## 使用方法 & 特性配置

请参阅 [文档](./source/features/README_CN.md) 或者在 [特性测试页面](https://font.subf.dev/zh-cn/playground) 尝试。

> [!note]
> 用于自定义构建的 Web 工具仍在开发中。

## 命名说明

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
- **CN / TC / JP / KR**: V8 CJK locale，分别对应简体中文、繁体中文、日文和韩文（使用对应后缀）
- **NF-CN / NF-TC / NF-JP / NF-KR**: 带 Nerd Font 图标的 CJK 版本
- **VF**: 发布包中的可变字体后缀；CJK 可变输出目录使用 `Variable-<LOCALE>`

### 字体微调

- **Hinted 字体** 用于低分辨率屏幕，以获得更好的渲染效果。根据我个人的经验，如果您的屏幕分辨率低于或等于 1080P，建议使用 "hinted 字体"。使用 "unhinted 字体" 会导致文本错位或粗细不均。
  - 在这种情况下，您可以选择 `MapleMono-TTF-AutoHint` / `MapleMono-NF` / `MapleMono-NF-CN` 等。
- **Unhinted 字体** 用于高分辨率屏幕（例如 MacBook）。使用 "hinted 字体" 会使您的文本模糊或看起来很奇怪。
  - 在这种情况下，您可以选择 `MapleMono-OTF` / `MapleMono-TTF` / `MapleMono-NF-unhinted` / `MapleMono-NF-CN-unhinted` 等。
- 为什么存在 `-AutoHint` 和 `-unhinted` 后缀？
  - 为了向后兼容，我保留了原始命名方案。`-AutoHint` 仅用于 `TTF` 格式。


## 自定义构建

[`config.json`](./config.json) 文件用于配置构建过程。查看 [schema](./source/schema.json) 或 [文档](./source/features/README.md) 了解更多详情。

命令行选项会覆盖 `config.json`。安装依赖后运行 `python build.py --help` 查看当前 CLI。

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

#### 4. 本地构建（V8 开发版）

V8 将合并到 `variable` 分支。请确保已安装 Python 3.10+ 和 `pip`。

```shell
git clone https://github.com/subframe7536/maple-font --depth 1 -b variable
cd maple-font
pip install -r requirements.txt
python build.py
```

> [!TIP]
> 对于 `Ubuntu` 或 `Debian`，可能还需要 `python-is-python3`
>
> 如果您在安装依赖项时遇到问题，只需创建一个新的 GitHub Codespace 并在那里运行命令

上述命令构建的是开发版，生成字体位于 `fonts/`，不会替换 Scoop、Homebrew、Arch、Nix 或 CDN 中已有的 V7.9 稳定包。

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

如果您想获得可变 Nerd Font，请在 `config.json` 中设置 `"nerd_font.variable": true` 或在构建脚本参数中添加 `--nf-variable`。该选项会将 NF 输出切换到 `Variable-NF`，发布包名称为 `NF-VF`。

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

1. `enable`: 单字替换固化到源轮廓，或通过 `calt` 启用上下文规则。
2. `disable`: 删除该特性规则。
3. `ignore`: 保留该 OpenType 特性供字体使用。

#### 自定义 OpenType 特性

OpenType 特性可以控制字体的内置变体和连字。您可以通过修改 OpenType 特性来删除一些不需要的连字或特征，修改特征的触发规则或添加一些新规则。

默认情况下，[`scripts/feature/`](./scripts/feature) 中的 Python 模块会生成 OpenType 特性字符串并在构建时加载。您可以在此处修改功能或自定义标签。

如果你想直接修改 OpenType 特性文件，请在运行 `build.py` 时添加 `--apply-fea-file`；匹配的 [`source/features/{regular,italic}{_cn,}.fea`](./source/features) 会应用到静态和可变字体路径。

### 无限箭头连字

受 Fira Code 的启发，本字体默认启用无限箭头连字。由于 Hinted 字体中的连字可能错位，Hinted 输出默认会关闭它；如需强制开启，请使用 `infinite_arrow` 或 `--infinite-arrow`。

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

### CJK 扩展版本

默认情况下不会生成 CJK 扩展字体。使用 `--cjk` 选择一个或多个 locale；可以重复参数或用逗号分隔：

```shell
# Maple Mono + 简体中文静态字体（默认）
python build.py --cjk cn

# Maple Mono + 繁体中文 + 日文静态字体
python build.py --cjk tc,jp

# Maple Mono + 日文可变字体
python build.py --cjk jp --cjk-variable

# 同时构建普通 CJK 和 Nerd Font CJK
python build.py --cjk cn --cjk-both
```

普通静态输出目录为 `fonts/CN/`、`fonts/TC/`、`fonts/JP/`、`fonts/KR/`；Nerd Font 静态输出使用 `fonts/NF-<LOCALE>/`；可变输出使用 `fonts/Variable-<LOCALE>/` 或 `fonts/Variable-NF-<LOCALE>/`。旧的 `--cn` 仍作为 `--cjk cn` 的兼容别名保留。

如果您想通过配置启用一个或多个 CJK locale，请在 [config.json](./config.json) 中使用 `cjk.locales.cn|jp|tc|kr`。完整的来源、回退顺序、缓存行为和独立基础字体构建流程请参阅 [`scripts/cjk/README.md`](./scripts/cjk/README.md)。

#### 缩小 CJK 字体的间距

如果您觉得 CJK 字符的间距**过大**，可以使用共享配置项 `cjk.narrow` 或命令行参数 `--cjk-narrow` 缩小间距，但是这将让字体无法被识别为严格等宽字体。

您可以在 [#249](https://github.com/subframe7536/maple-font/issues/249#issuecomment-2871260476) 中查看效果。

如果您也想改变拉丁字母的宽度，请使用 [`--width` 参数](#窄字符)

#### GitHub 镜像

构建脚本将自动从 GitHub 下载所需的资源。如果您在下载时遇到问题，请在 [config.json](./config.json) 中设置 `github_mirror` 或将 `$GITHUB` 设置为您的环境变量。（目标 URL 为 `https://<github_mirror>/<user>/<repo>/releases/download/<tag>/<file>`），或者直接下载目标 `.zip` 文件并将其放在与 `build.py` 相同的目录中。

#### 繁體中文標點符號支援

通過開啟 `cv99`，所有的中文標點符號都會居中，詳情見 [#150](https://github.com/subframe7536/maple-font/issues/150)

### 构建脚本用法

使用 `python build.py --help` 查看完整 CLI。常用选项如下：

| 选项 | 作用 |
| --- | --- |
| `--format ttf,otf,woff2` | 选择基础输出格式；可变基础字体始终构建。 |
| `--nf` / `--no-nf` | 开启或关闭 Nerd Font 输出，默认开启。 |
| `--nf-variable` | 构建可变 Nerd Font。 |
| `--hinted` / `--no-hinted` | 选择 NF 和静态 CJK 合并使用的基础字体。 |
| `--width {default,narrow,slim}` | 将拉丁字宽设置为 600、550 或 500 units。 |
| `--feat zero,cv01,ss07` | 将指定 OpenType 特性冻结到构建结果中。 |
| `--cache` | 重用 `fonts/` 下已验证的阶段。 |
| `--debug` | 只构建较小的常规/斜体测试输出，不构建 OTF、WOFF2 或 NF。 |

CJK 使用 `--cjk <locale>`，并按需组合 `--cjk-variable`、`--cjk-narrow`、`--cjk-hinted` 或 `--cjk-both`。旧的 `--cn` 系列仅作为兼容别名，新脚本请使用 `--cjk`。

## 开发与维护

维护者和 coding agent 请先阅读 [`AGENTS.md`](./AGENTS.md)，再根据任务使用 [`scripts/README.md`](./scripts/README.md)、[`scripts/cjk/README.md`](./scripts/cjk/README.md) 和 [`scripts/maintenance.md`](./scripts/maintenance.md)。`fonts/`、CJK 字体、压缩包和生成的 `.fea` 文件都不能手工编辑；配置检查可运行 `uv run build.py --dry`。

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
