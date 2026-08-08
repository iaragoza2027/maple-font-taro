# Naming and Choosing Fonts

<!--todo)) 用表格的方式。v8新增了宽度，需要添加-->

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
